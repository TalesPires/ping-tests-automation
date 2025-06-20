from django.db import models
from django.utils.translation import gettext_lazy as _


class NetworkTestResult(models.Model):
    telnet_host = models.CharField(max_length=100)
    telnet_port = models.PositiveIntegerField()
    ping_destination = models.CharField(max_length=100)
    test_name = models.CharField(max_length=100, null=True)
    sw_name = models.CharField(max_length=100)
    test_start = models.DateTimeField()
    test_end = models.DateTimeField()
    statistics = models.TextField()
    error_message = models.TextField(blank=True, null=True)
    

    def __str__(self):
        return f"{self.sw_name} ({self.telnet_host}:{self.telnet_port}) = {self.test_name} - {self.ping_destination} [{self.test_start} - {self.test_end}]"
    
    class escolhas_success(models.TextChoices):
        FALHA_TOTAL = "FT",_("Falha Total")
        FALHA_PARCIAL = "FP",_("Falha Parcial")
        SEM_FALHA = "SF",_("Sem Falha")

    success = models.CharField(
        max_length=2,
        choices=escolhas_success.choices,
        default=escolhas_success.SEM_FALHA,
    )
    
class NetworkTestScenario(models.Model):
    source_ip = models.GenericIPAddressField()
    source_port = models.IntegerField()
    dest_ip = models.GenericIPAddressField()
    device_name = models.CharField(max_length=50)
    test_name = models.CharField(max_length=75)
    active = models.BooleanField(default=True)
