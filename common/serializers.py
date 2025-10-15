from rest_framework import serializers
from .models import Address, Contact, Company, Location, Category

class AddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = Address
        fields = '__all__'

class ContactSerializer(serializers.ModelSerializer):
    class Meta:
        model = Contact
        fields = '__all__'

class CompanySerializer(serializers.ModelSerializer):
    address = AddressSerializer(required=False)
    contact = ContactSerializer(required=False)

    class Meta:
        model = Company
        fields = '__all__'

class CommonLocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Location
        fields = '__all__'

class CommonCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = '__all__'


