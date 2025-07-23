from datetime import timedelta
import logging
from django_q.tasks import async_task, schedule
from django_q.models import Schedule
from django.utils import timezone
from django.db import close_old_connections
from .ssh_client import SSHClient
from pingtest.models import NetworkTestResult, NetworkTestScenario
from django.core.cache import cache
from django.db import transaction
import threading
import time


logger = logging.getLogger(__name__)

class NetworkTestScheduler:
    def __init__(self, interval_minutes=5):
        self.ssh_client = SSHClient()
        self.interval = interval_minutes
        self.schedule_name = "network_test_schedule"
        self.task_timeout = 300 
        
    
    def start_polling_scheduler(self, poll_interval=360):
        """
        Starts a background thread that periodically checks for new, removed, or changed scenarios
        and updates the schedule accordingly.
        """
        def polling_loop():
            # Maps scenario.id -> last scheduled tuple
            scheduled = {}
            logger.info("Starting background polling scheduler loop.")
            while True:
                # Build current scenarios dict: id -> tuple
                scenarios = {
                    s.id: (
                        s.source_ip,
                        s.source_port,
                        s.dest_ip,
                        s.device_name,
                        s.test_name,
                    )
                    for s in NetworkTestScenario.objects.filter(active=True)
                }

                # Handle new or changed scenarios
                for scenario_id, scenario_tuple in scenarios.items():
                    if scenario_id not in scheduled:
                        # New scenario: schedule it
                        if self._validate_scenario(scenario_tuple):
                            self._schedule_next(scenario_tuple)
                            logger.info(f"Scheduled scenario: {scenario_tuple[3]} ({scenario_tuple[4]})")
                        scheduled[scenario_id] = scenario_tuple
                    elif scheduled[scenario_id] != scenario_tuple:
                        # Scenario changed: remove old schedule, add new
                        old_tuple = scheduled[scenario_id]
                        sched_name = f"{self.schedule_name}_{old_tuple[3]}_{old_tuple[2]}"
                        Schedule.objects.filter(name=sched_name).delete()
                        logger.info(f"Removed old schedule for scenario: {old_tuple[3]} ({old_tuple[4]})")
                        if self._validate_scenario(scenario_tuple):
                            self._schedule_next(scenario_tuple)
                            logger.info(f"Rescheduled scenario: {scenario_tuple[3]} ({scenario_tuple[4]})")
                        scheduled[scenario_id] = scenario_tuple

                # Handle removed scenarios
                for scenario_id in list(scheduled.keys()):
                    if scenario_id not in scenarios:
                        old_tuple = scheduled[scenario_id]
                        sched_name = f"{self.schedule_name}_{old_tuple[3]}_{old_tuple[2]}"
                        Schedule.objects.filter(name=sched_name).delete()
                        logger.info(f"Removed schedule for deleted scenario: {old_tuple[3]} ({old_tuple[4]})")
                        del scheduled[scenario_id]

                time.sleep(poll_interval)

        thread = threading.Thread(target=polling_loop, daemon=True)
        thread.start()

    def _save_result(self, result):
        """Enhanced database save with list handling"""
        try:
            close_old_connections()
            
            # Handle list results
            if isinstance(result, list):
                for res in result:
                    self._save_single_result(res)
                return
                
            # Handle single result
            self._save_single_result(result)
            
        except Exception as e:
            logger.error(f"DB Save Error: {str(e)}", exc_info=True)
        finally:
            close_old_connections()

    def _save_single_result(self, result):
        """Handle individual result saving"""
        if not isinstance(result, dict):
            logger.error(f"Invalid result type: {type(result)}")
            return

        NetworkTestResult.objects.update_or_create(
            telnet_host=result.get('telnet_host'),
            telnet_port=result.get('telnet_port'),
            ping_destination=result.get('ping_destination'),
            test_name=result.get('test_name'),
            sw_name=result.get('sw_name'),
            test_start=result.get('start_time'),
            defaults={
                'test_end': result.get('end_time'),
                'statistics': str(result.get('statistics', ''))[:500],
                'success': result.get('success', 'FT'),
                'error_message': str(result.get('error', ''))[:2000]
            }
        )

    @staticmethod
    def create_task(scenario):
        """Static method wrapper for task creation"""
        scheduler = NetworkTestScheduler()  # Or get existing instance
        return scheduler._create_task_impl(scenario)

    def _create_task_impl(self, scenario):
        """Actual task implementation"""
        try:
            logger.info(f"Starting task for {scenario}")
            if not self._validate_scenario(scenario):
                logger.error(f"Invalid scenario format: {scenario}")
                return None

            result = self._execute_test(scenario)
            self._save_result(result)
            return result
        except Exception as e:
            logger.error(f"Task failed: {str(e)}", exc_info=True)
            return self._create_error_result(e, scenario)

    def _validate_scenario(self, scenario):
        """Validate scenario format before execution"""
        return isinstance(scenario, (list, tuple)) and len(scenario) == 5

    def _execute_test(self, scenario):
        """Execute the actual network test"""
        telnet_host, telnet_port, ping_dest, sw_name, test_name = scenario
        
        try:
            logger.debug(f"Testing {sw_name} ({telnet_host}:{telnet_port})")
            
            # Change repeat to 1 since scheduling handles repetitions
            results = self.ssh_client.run_test(
                telnet_host=telnet_host,
                telnet_port=telnet_port,
                ping_destination=ping_dest,
                sw_name=sw_name,
                repeat=1  
            )
            
            if isinstance(results, list) and len(results) > 0:
                results[0]['test_name'] = test_name  # Add test_name to the result
                return results[0]
        
            if isinstance(results, dict):
                results['test_name'] = test_name  # Add test_name to the result
                return results
            
            # If results are empty or invalid, return an error result
            return self._create_error_result("No results returned", scenario)
        
        except Exception as e:
            return self._create_error_result(e, scenario)

    def _create_error_result(self, error, scenario):
        """Generate error result structure"""
        return {
            'telnet_host': scenario[0] if len(scenario) > 0 else 'unknown',
            'telnet_port': scenario[1] if len(scenario) > 1 else 0,
            'ping_destination': scenario[2] if len(scenario) > 2 else 'unknown',
            'test_name': scenario[2] if len(scenario) > 2 else 'unknown',
            'sw_name': scenario[3] if len(scenario) > 3 else 'unknown',
            'start_time': timezone.localtime(),
            'end_time': timezone.localtime(),
            'success': 'FT',
            'error': str(error)[:1000],
            'statistics': ''
        }

    def _schedule_next(self, scenario):
        """Schedule next execution using static reference"""
        schedule(
            'pingtest.utils.test_runner.NetworkTestScheduler.create_task',
            scenario,
            name=f"{self.schedule_name}_{scenario[3]}_{scenario[2]}",
            schedule_type='C',
            cron='*/7 * * * *', # repeats every 7 minutes
            repeats=-1,
        )

    def _process_scenario(self, scenario):
        """Actual task processing"""
        try:
            logger.info(f"Processing scenario: {scenario}")
            result = self._execute_test(scenario)
            self._save_result(result)
            
            # Schedule next run after successful execution
            self._schedule_next(scenario)  
            
            return result
        except Exception as e:
            logger.error(f"Task failed: {str(e)}", exc_info=True)
            return self._create_error_result(e, scenario)


    def start_scheduler(self, scenarios):
        """Initialize tasks using static reference"""
        
        self._cleanup_existing_schedules()
        
        for scenario in scenarios:
            if self._validate_scenario(scenario):
                self._schedule_next(scenario)  
                logger.info(f"Scheduled {scenario[3]}")


    def _handle_task_result(self, task):
        """Handle both success and failure states"""
        if task.success:
            logger.info(f"Task completed for {task.result.get('sw_name', 'unknown')}")
            self._save_result(task.result)
        else:
            logger.error(f"Task failed: {task.result}")
            error_result = self._create_error_result(
                Exception(task.result),
                task.args[0] if task.args else []
            )
            self._save_result(error_result)

    def _cleanup_existing_schedules(self):
        """Remove existing schedules to prevent duplicates"""
        Schedule.objects.filter(name__startswith=self.schedule_name).delete()
        
    

class CacheManager:
    def schedule_cache_refresh():
        schedule(
            'pingtest.utils.test_runner.CacheManager.refresh_cache',
            name=f'cache_refresh_{timezone.localtime()}',
            schedule_type='C',
            cron='*/7 * * * *',
            repeats=-1
        )
        
    def refresh_cache():
        """Force update all results and cache"""
        try:
            results = NetworkTestResult.objects.order_by('-test_end')[:50]  # Descending
            cache.set('cached_results', results, 360) 
            logger.info(f"Cache updated with {len(results)} records")
        except Exception as e:
            logger.error(f"Cache refresh failed: {str(e)}")
            cache.set('cached_results', [], 360) 
        
    def _cleanup_existing_cache():
        """Remove existing schedules to prevent duplicates"""
        Schedule.objects.filter(name__startswith='cache_refresh_').delete()
    
    
class CleanupManager:
    def cleanup_old_results():
        """Cleanup results older than retention period"""
        try:
            # Tempo de corte das tabelas
            cutoff = timezone.now() - timezone.timedelta(hours=18)

            with transaction.atomic():
                while True:
                    batch = list(NetworkTestResult.objects.filter(test_start__lt=cutoff)[:1000])
                    if not batch:
                        break
                    NetworkTestResult.objects.filter(id__in=[record.id for record in batch]).delete()
                    logger.info(f"Deleted a batch of {len(batch)} old records.")

            logger.info("Cleanup completed successfully.")
            return "Cleaned up old records"

        except Exception as e:
            logger.error(f"Cleanup failed: {str(e)}", exc_info=True)
            raise
    
    def schedule_cleanup():
        """Schedule cleanup every 12 hours"""
        schedule(
            'pingtest.utils.test_runner.CleanupManager.cleanup_old_results',
            schedule_type='C',
            cron='0 */6 * * *',  
            name='db_cleanup',
            repeats=-1,
        )
    