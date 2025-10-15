from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    MainCategoryViewSet, SubCategoryViewSet, CategoryViewSet, 
    LocationViewSet, ProductViewSet, StockViewSet,
    BillOfMaterialsViewSet, BOMItemViewSet, 
    AssemblyOrderViewSet, AssemblyOrderItemViewSet, StockMovementViewSet, GoodsReceiptViewSet
)

router = DefaultRouter()
router.register(r'main-categories', MainCategoryViewSet)
router.register(r'sub-categories', SubCategoryViewSet)
router.register(r'categories', CategoryViewSet)
router.register(r'locations', LocationViewSet)
router.register(r'products', ProductViewSet)
router.register(r'stock', StockViewSet)
router.register(r'stock-movements', StockMovementViewSet, basename='stock-movement')
router.register(r'boms', BillOfMaterialsViewSet)
router.register(r'bom-items', BOMItemViewSet)
router.register(r'assembly-orders', AssemblyOrderViewSet)
router.register(r'assembly-order-items', AssemblyOrderItemViewSet)
router.register(r'goods-receipts', GoodsReceiptViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
