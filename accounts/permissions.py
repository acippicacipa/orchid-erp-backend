from rest_framework import permissions

class IsAdminOrSales(permissions.BasePermission):
    """
    Custom permission to only allow admins or sales users to access sales-related objects.
    """
    def has_permission(self, request, view):
        if request.user and request.user.is_authenticated:
            return request.user.profile.has_role("ADMIN") or request.user.profile.has_role("SALES")
        return False

class IsAdminOrWarehouse(permissions.BasePermission):
    """
    Custom permission to only allow admins or warehouse users to access inventory-related objects.
    """
    def has_permission(self, request, view):
        if request.user and request.user.is_authenticated:
            return request.user.profile.has_role("ADMIN") or request.user.profile.has_role("WAREHOUSE")
        return False

class IsAdminOrPurchasing(permissions.BasePermission):
    """
    Custom permission to only allow admins or purchasing users to access purchasing-related objects.
    """
    def has_permission(self, request, view):
        if request.user and request.user.is_authenticated:
            return request.user.profile.has_role("ADMIN") or request.user.profile.has_role("PURCHASING")
        return False

class IsAdminOrAccounting(permissions.BasePermission):
    """
    Custom permission to only allow admins or accounting users to access accounting-related objects.
    """
    def has_permission(self, request, view):
        if request.user and request.user.is_authenticated:
            return request.user.profile.has_role("ADMIN") or request.user.profile.has_role("ACCOUNTING")
        return False

class IsAdminOrAudit(permissions.BasePermission):
    """
    Custom permission to only allow admins or audit users to access all objects (read-only for audit).
    """
    def has_permission(self, request, view):
        if request.user and request.user.is_authenticated:
            if request.user.profile.has_role("ADMIN"):
                return True
            if request.user.profile.has_role("AUDIT") and request.method in permissions.SAFE_METHODS:
                return True
        return False

class IsOwnerOrAdmin(permissions.BasePermission):
    """
    Custom permission to only allow owners of an object or admins to edit it.
    """
    def has_object_permission(self, request, view, obj):
        if request.user and request.user.is_authenticated:
            if request.user.profile.has_role("ADMIN"):
                return True
            # Assuming the object has a 'user' field or 'created_by' field
            if hasattr(obj, 'user') and obj.user == request.user:
                return True
            if hasattr(obj, 'created_by') and obj.created_by == request.user:
                return True
        return False



class CanImportData(permissions.BasePermission):
    """
    Custom permission to allow data import based on user role and import type.
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Admin can import any data
        if request.user.profile.has_role("ADMIN"):
            return True
        
        # Check specific import permissions based on template type
        template_id = request.data.get('template_id') or request.query_params.get('template_id')
        if template_id:
            try:
                from data_import.models import ImportTemplate
                template = ImportTemplate.objects.get(id=template_id)
                return self._can_import_template_type(request.user, template.template_type)
            except ImportTemplate.DoesNotExist:
                return False
        
        # For general import operations (like viewing history), allow authenticated users
        return True
    
    def _can_import_template_type(self, user, template_type):
        """Check if user can import specific template type"""
        # Sales module imports
        if template_type in ['CUSTOMERS', 'SALES_ORDERS', 'INVOICES', 'PAYMENTS']:
            return user.profile.has_role("SALES")
        
        # Inventory module imports
        if template_type in ['ITEMS', 'CATEGORIES', 'INVENTORY']:
            return user.profile.has_role("WAREHOUSE")
        
        # Purchasing module imports
        if template_type in ['SUPPLIERS', 'PURCHASE_ORDERS', 'BILLS', 'SUPPLIER_PAYMENTS']:
            return user.profile.has_role("PURCHASING")
        
        # Accounting module imports
        if template_type in ['ACCOUNTS', 'JOURNAL_ENTRIES', 'JOURNAL_ITEMS', 'LEDGERS']:
            return user.profile.has_role("ACCOUNTING")
        
        # Common imports (locations, users) - only admin
        if template_type in ['LOCATIONS', 'USERS']:
            return user.profile.has_role("ADMIN")
        
        return False

class CanViewImportHistory(permissions.BasePermission):
    """
    Permission to view import history based on user role.
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Admin and Audit can view all import history
        if request.user.profile.has_role("ADMIN") or request.user.profile.has_role("AUDIT"):
            return True
        
        # Other users can only view their own import history
        return True
    
    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Admin and Audit can view all imports
        if request.user.profile.has_role("ADMIN") or request.user.profile.has_role("AUDIT"):
            return True
        
        # Users can only view their own imports
        return obj.created_by == request.user

class CanDownloadTemplates(permissions.BasePermission):
    """
    Permission to download import templates based on user role.
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Admin can download any template
        if request.user.profile.has_role("ADMIN"):
            return True
        
        # Check specific template permissions
        template_id = request.query_params.get('template_id')
        if template_id:
            try:
                from data_import.models import ImportTemplate
                template = ImportTemplate.objects.get(id=template_id)
                return self._can_download_template_type(request.user, template.template_type)
            except ImportTemplate.DoesNotExist:
                return False
        
        # For listing templates, allow authenticated users (they'll see filtered list)
        return True
    
    def _can_download_template_type(self, user, template_type):
        """Check if user can download specific template type"""
        # Sales module templates
        if template_type in ['CUSTOMERS', 'SALES_ORDERS', 'INVOICES', 'PAYMENTS']:
            return user.profile.has_role("SALES")
        
        # Inventory module templates
        if template_type in ['ITEMS', 'CATEGORIES', 'INVENTORY']:
            return user.profile.has_role("WAREHOUSE")
        
        # Purchasing module templates
        if template_type in ['SUPPLIERS', 'PURCHASE_ORDERS', 'BILLS', 'SUPPLIER_PAYMENTS']:
            return user.profile.has_role("PURCHASING")
        
        # Accounting module templates
        if template_type in ['ACCOUNTS', 'JOURNAL_ENTRIES', 'JOURNAL_ITEMS', 'LEDGERS']:
            return user.profile.has_role("ACCOUNTING")
        
        # Common templates (locations, users) - only admin
        if template_type in ['LOCATIONS', 'USERS']:
            return user.profile.has_role("ADMIN")
        
        return False

