from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from .models import UserProfile, Permission


@admin.register(Permission)
class PermissionAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'category', 'description']
    list_filter = ['category']
    search_fields = ['code', 'name']
    ordering = ['category', 'code']


class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    verbose_name_plural = '用户角色和权限'
    filter_horizontal = ['permissions']
    fieldsets = (
        ('基本信息', {
            'fields': ('role', 'phone', 'department')
        }),
        ('额外权限', {
            'fields': ('permissions',),
            'description': '可以为用户配置额外的权限，这些权限会叠加在角色默认权限之上。'
        }),
    )


class UserAdmin(BaseUserAdmin):
    inlines = [UserProfileInline]
    
    # 重写fieldsets，完全移除Django默认的权限和组字段
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('个人信息', {'fields': ('first_name', 'last_name', 'email')}),
        ('重要日期', {'fields': ('last_login', 'date_joined')}),
        ('状态', {'fields': ('is_active', 'is_staff', 'is_superuser')}),
    )
    
    # 添加用户时的字段（不包含权限和组）
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'password1', 'password2'),
        }),
    )
    
    # 移除权限和组字段
    filter_horizontal = []
    
    # 列表页显示的字段
    list_display = ['username', 'email', 'first_name', 'last_name', 'is_staff', 'is_active', 'date_joined']
    
    # 列表页过滤器
    list_filter = ['is_staff', 'is_active', 'date_joined']


admin.site.unregister(User)
admin.site.register(User, UserAdmin)
