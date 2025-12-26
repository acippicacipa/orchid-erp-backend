from rest_framework.routers import DefaultRouter
from .views import SupplierViewSet, PurchaseOrderViewSet, PurchaseOrderItemViewSet, BillViewSet, SupplierPaymentViewSet, PurchaseReturnViewSet

router = DefaultRouter()
router.register(r'suppliers', SupplierViewSet)
router.register(r'purchase-orders', PurchaseOrderViewSet)
router.register(r'purchase-order-items', PurchaseOrderItemViewSet)
router.register(r'bills', BillViewSet)
router.register(r'supplier-payments', SupplierPaymentViewSet)
router.register(r'purchase-returns', PurchaseReturnViewSet)

urlpatterns = router.urls


