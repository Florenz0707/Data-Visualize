"""
Django Story Platform - 媒体序列化器
"""
from rest_framework import serializers
from models import MediaFile, MediaLibrary, MediaAsset


class MediaFileSerializer(serializers.ModelSerializer):
    """媒体文件序列化器"""
    story = serializers.StringRelatedField(read_only=True)
    file_size_mb = serializers.ReadOnlyField()
    
    class Meta:
        model = MediaFile
        fields = [
            'id', 'story', 'file_type', 'file_path', 'file_name',
            'file_size', 'file_size_mb', 'mime_type', 'metadata', 'created_at'
        ]
        read_only_fields = ['id', 'story', 'created_at']


class MediaLibrarySerializer(serializers.ModelSerializer):
    """媒体库序列化器"""
    user = serializers.StringRelatedField(read_only=True)
    assets_count = serializers.SerializerMethodField()
    
    class Meta:
        model = MediaLibrary
        fields = [
            'id', 'user', 'name', 'description', 'is_public',
            'created_at', 'updated_at', 'assets_count'
        ]
        read_only_fields = ['id', 'user', 'created_at', 'updated_at']
    
    def get_assets_count(self, obj):
        return obj.assets.count()


class MediaLibraryCreateSerializer(serializers.ModelSerializer):
    """媒体库创建序列化器"""
    
    class Meta:
        model = MediaLibrary
        fields = ['name', 'description', 'is_public']
    
    def validate_name(self, value):
        if len(value.strip()) < 2:
            raise serializers.ValidationError("Library name must be at least 2 characters")
        return value.strip()


class MediaAssetSerializer(serializers.ModelSerializer):
    """媒体资产序列化器"""
    library = serializers.StringRelatedField(read_only=True)
    file_size_mb = serializers.ReadOnlyField()
    
    class Meta:
        model = MediaAsset
        fields = [
            'id', 'library', 'asset_type', 'file_path', 'file_name',
            'file_size', 'file_size_mb', 'mime_type', 'metadata',
            'tags', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'library', 'created_at', 'updated_at']


class MediaAssetCreateSerializer(serializers.ModelSerializer):
    """媒体资产创建序列化器"""
    
    class Meta:
        model = MediaAsset
        fields = ['asset_type', 'file_path', 'file_name', 'file_size', 'mime_type', 'metadata', 'tags']
    
    def validate_file_size(self, value):
        # 限制文件大小（例如：100MB）
        max_size = 100 * 1024 * 1024  # 100MB
        if value > max_size:
            raise serializers.ValidationError(f"File size cannot exceed {max_size // (1024*1024)}MB")
        return value


class MediaUploadSerializer(serializers.Serializer):
    """媒体上传序列化器"""
    file = serializers.FileField()
    asset_type = serializers.ChoiceField(choices=['image', 'audio', 'video', 'template'])
    library_id = serializers.UUIDField()
    tags = serializers.ListField(
        child=serializers.CharField(max_length=50),
        required=False,
        allow_empty=True
    )
    metadata = serializers.JSONField(required=False, default=dict)
    
    def validate_file(self, value):
        # 验证文件类型
        allowed_types = {
            'image': ['image/jpeg', 'image/png', 'image/gif', 'image/webp'],
            'audio': ['audio/mpeg', 'audio/wav', 'audio/ogg'],
            'video': ['video/mp4', 'video/avi', 'video/mov'],
            'template': ['application/json', 'text/plain']
        }
        
        asset_type = self.initial_data.get('asset_type')
        if asset_type and value.content_type not in allowed_types.get(asset_type, []):
            raise serializers.ValidationError(f"Invalid file type for {asset_type}")
        
        return value
    
    def validate_library_id(self, value):
        try:
            library = MediaLibrary.objects.get(id=value)
            # 检查用户权限
            request = self.context.get('request')
            if request and request.user != library.user:
                raise serializers.ValidationError("You don't have permission to upload to this library")
        except MediaLibrary.DoesNotExist:
            raise serializers.ValidationError("Media library not found")
        return value
