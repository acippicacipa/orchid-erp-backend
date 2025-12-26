from rest_framework.routers import DefaultRouter
from django.urls import path, include
from .views import (
    CustomerViewSet, CustomerGroupViewSet, SalesOrderViewSet, SalesOrderItemViewSet, 
    InvoiceViewSet, PaymentViewSet, ProductSearchViewSet,
    DownPaymentViewSet, DownPaymentUsageViewSet, DeliveryOrderViewSet, SalesReturnViewSet,
    ConsignmentShipmentViewSet, ConsignmentSalesReportViewSet
)

router = DefaultRouter()
router.register(r'customers', CustomerViewSet)
router.register(r'customer-groups', CustomerGroupViewSet)
router.register(r'sales-orders', SalesOrderViewSet)
router.register(r'sales-order-items', SalesOrderItemViewSet)
router.register(r'invoices', InvoiceViewSet)
router.register(r'payments', PaymentViewSet)
router.register(r'products', ProductSearchViewSet, basename='sales-products')
router.register(r'delivery-orders', DeliveryOrderViewSet)
router.register(r'sales-returns', SalesReturnViewSet)
router.register(r'consignment-shipments', ConsignmentShipmentViewSet)
router.register(r'consignment-sales-reports', ConsignmentSalesReportViewSet)

# Down Payment endpoints
router.register(r'down-payments', DownPaymentViewSet)
router.register(r'down-payment-usage', DownPaymentUsageViewSet)

urlpatterns = [
    path('', include(router.urls)),
]


