from django.core.management.base import BaseCommand
from data_import.services import TemplateService

class Command(BaseCommand):
    help = 'Set up default import templates'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Setting up default import templates...'))
        
        TemplateService.create_default_templates()
        
        self.stdout.write(self.style.SUCCESS('Default import templates created successfully!'))

