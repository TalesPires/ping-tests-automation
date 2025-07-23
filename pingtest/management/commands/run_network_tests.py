from django.core.management.base import BaseCommand
from pingtest.models import NetworkTestScenario
from pingtest.utils.test_runner import NetworkTestScheduler
from pingtest.utils.test_runner import CacheManager, CleanupManager
import logging
from django_q.cluster import Cluster
import time
from django_q.models import Schedule 

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Execute network tests using Django Q scheduler'

    def add_arguments(self, parser):
        parser.add_argument(
            '--stop',
            action='store_true',
            help='Stop all scheduled tests'
        )    

    def handle(self, *args, **options):
        if options['stop']:
            scheduler = NetworkTestScheduler()
            scheduler._cleanup_existing_schedules()
            CacheManager._cleanup_existing_cache()
            Schedule.objects.filter(name='db_cleanup').delete()
            self.stdout.write(self.style.SUCCESS("All scheduled tests stopped"))
            return

        CleanupManager.schedule_cleanup()
        CacheManager.schedule_cache_refresh()
        
        self.stdout.write(self.style.SUCCESS(
            "Keep the Django Q cluster running with:\n"
            "python manage.py qcluster"
        ))      
    
        test_scenarios = [
            (
                s.source_ip,
                s.source_port,
                s.dest_ip,
                s.device_name,
                s.test_name,
            )
            for s in NetworkTestScenario.objects.filter(active=True)]
        
        
        scheduler = NetworkTestScheduler()
        scheduler.start_polling_scheduler(poll_interval=360) 
        
        try:
            while True:
                time.sleep(360)
        except KeyboardInterrupt:
            print("Shutting down polling scheduler...")
    