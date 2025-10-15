from rest_framework.routers import DefaultRouter
from .views import (
    CustomerViewSet, SalesOrderViewSet, SalesOrderItemViewSet, 
    InvoiceViewSet, PaymentViewSet, ProductSearchViewSet,
    DownPaymentViewSet, DownPaymentUsageViewSet
)
from .discount_views import (
    CustomerGroupViewSet, ProductDiscountViewSet, QuantityDiscountViewSet,
    WholesalerDiscountViewSet, PriceCalculationViewSet
)

router = DefaultRouter()
router.register(r'customers', CustomerViewSet)
router.register(r'sales-orders', SalesOrderViewSet)
router.register(r'sales-order-items', SalesOrderItemViewSet)
router.register(r'invoices', InvoiceViewSet)
router.register(r'payments', PaymentViewSet)
router.register(r'products', ProductSearchViewSet, basename='sales-products')

# Down Payment endpoints
router.register(r'down-payments', DownPaymentViewSet)
router.register(r'down-payment-usage', DownPaymentUsageViewSet)

# Discount Management endpoints
router.register(r'customer-groups', CustomerGroupViewSet)
router.register(r'product-discounts', ProductDiscountViewSet)
router.register(r'quantity-discounts', QuantityDiscountViewSet)
router.register(r'wholesaler-discounts', WholesalerDiscountViewSet)
router.register(r'price-calculation', PriceCalculationViewSet, basename='price-calculation')

urlpatterns = router.urls


