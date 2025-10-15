from django.core.management.base import BaseCommand
from accounts.models import UserRole, UserProfile
from common.models import Contact

class Command(BaseCommand):
    help = 'Set up initial ERP data including roles and admin user'

    def add_arguments(self, parser):
        parser.add_argument(
            '--admin-username',
            type=str,
            default='admin',
            help='Admin username (default: admin)'
        )
        parser.add_argument(
            '--admin-password',
            type=str,
            default='admin123',
            help='Admin password (default: admin123)'
        )
        parser.add_argument(
            '--admin-email',
            type=str,
            default='admin@orchid-erp.com',
            help='Admin email (default: admin@orchid-erp.com)'
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Setting up Orchid ERP...'))
        
        # Create default roles
        self.stdout.write('Creating default user roles...')
        UserRole.create_default_roles()
        
        # Get admin role
        admin_role = UserRole.objects.get(name='ADMIN')
        
        # Create admin user if it doesn't exist
        admin_username = options['admin_username']
        admin_password = options['admin_password']
        admin_email = options['admin_email']
        
        user, created = User.objects.get_or_create(
            username=admin_username,
            defaults={
                'email': admin_email,
                'first_name': 'System',
                'last_name': 'Administrator',
                'is_staff': True,
                'is_superuser': True,
            }
        )
        
        if created:
            user.set_password(admin_password)
            user.save()
            self.stdout.write(
                self.style.SUCCESS(f'Created admin user: {admin_username}')
            )
        else:
            self.stdout.write(
                self.style.WARNING(f'Admin user already exists: {admin_username}')
            )
        
        # Create user profile if it doesn't exist
        profile, created = UserProfile.objects.get_or_create(
            user=user,
            defaults={
                'role': admin_role,
                'employee_id': 'EMP001',
                'department': 'IT',
                'position': 'System Administrator',
            }
        )
        
        if created:
            self.stdout.write(
                self.style.SUCCESS('Created admin user profile')
            )
        else:
            self.stdout.write(
                self.style.WARNING('Admin user profile already exists')
            )
        
        # Display setup information
        self.stdout.write('\n' + '='*50)
        self.stdout.write(self.style.SUCCESS('Orchid ERP Setup Complete!'))
        self.stdout.write('='*50)
        self.stdout.write(f'Admin Username: {admin_username}')
        self.stdout.write(f'Admin Password: {admin_password}')
        self.stdout.write(f'Admin Email: {admin_email}')
        self.stdout.write('='*50)
        
        # Display available roles
        self.stdout.write('\nAvailable User Roles:')
        for role in UserRole.objects.all():
            self.stdout.write(f'  - {role.name}: {role.display_name}')
        
        self.stdout.write('\nYou can now start the development server with:')
        self.stdout.write('  python manage.py runserver 0.0.0.0:8000')
        self.stdout.write('\nAPI will be available at: http://localhost:8000/api/')
        self.stdout.write('Admin panel at: http://localhost:8000/admin/')
        self.stdout.write('')

