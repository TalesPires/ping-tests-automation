from django import forms
from django.core.exceptions import ValidationError
from .models import NetworkTestScenario

class NetworkTestScenarioForm(forms.ModelForm):
    class Meta:
        model = NetworkTestScenario
        fields = [
            'source_ip',
            'source_port',
            'dest_ip',
            'device_name',
            'test_name',
            'active',
        ]