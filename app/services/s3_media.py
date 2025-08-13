"""
S3 service for media file upload and management
"""

import uuid
from datetime import datetime, timedelta
from typing import Optional
import boto3
from botocore.exceptions import ClientError

from ..config import settings
from ..utils.errors import S3Error
from ..utils.logging import get_logger

logger = get_logger(__name__)


class S3MediaService:
    """S3 service for uploading and managing media files"""
    
    def __init__(self):
        self.s3_client = boto3.client(
            's3',
            region_name=settings.aws_region,
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key
        )
        self.bucket_name = settings.s3_bucket
    
    def _generate_audio_key(self, user_id: str, file_extension: str = "mp3") -> str:
        """Generate a unique S3 key for audio files"""
        
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        unique_id = str(uuid.uuid4())[:8]
        
        # Sanitize user_id for filename
        safe_user_id = "".join(c for c in user_id if c.isalnum() or c in "_-")[:20]
        
        return f"audio/{safe_user_id}/{timestamp}_{unique_id}.{file_extension}"
    
    async def upload_audio(
        self,
        audio_data: bytes,
        user_id: str,
        content_type: str = "audio/mpeg",
        file_extension: str = "mp3"
    ) -> str:
        """
        Upload audio data to S3 and return a presigned URL for public access
        
        Args:
            audio_data: Audio file bytes
            user_id: User identifier for organizing files
            content_type: MIME type of the audio
            file_extension: File extension for the audio
            
        Returns:
            Time-limited presigned URL of the uploaded audio file
        """
        
        s3_key = self._generate_audio_key(user_id, file_extension)
        try:
            # Log intent
            logger.info(f"Uploading audio to S3: {s3_key}, size: {len(audio_data)} bytes")
            
            # Upload to S3 without ACLs (BucketOwnerEnforced)
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=s3_key,
                Body=audio_data,
                ContentType=content_type,
                CacheControl='max-age=86400',
                Metadata={
                    'user_id': user_id,
                    'upload_time': datetime.utcnow().isoformat(),
                    'content_type': content_type
                }
            )
            
            # Generate a presigned GET URL so Twilio can fetch it
            presigned_url = self.s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': self.bucket_name, 'Key': s3_key},
                ExpiresIn=24 * 60 * 60  # 24 hours
            )
            
            logger.info(f"Successfully uploaded audio to S3 (presigned): {s3_key}")
            
            return presigned_url
            
        except ClientError as e:
            error_msg = f"Failed to upload audio to S3: {str(e)}"
            logger.error(error_msg)
            raise S3Error(error_msg, bucket=self.bucket_name, key=s3_key)
        except Exception as e:
            error_msg = f"Unexpected error during S3 upload: {str(e)}"
            logger.error(error_msg)
            raise S3Error(error_msg, bucket=self.bucket_name)
    
    async def download_audio(self, s3_url: str) -> bytes:
        """
        Download audio file from S3 URL
        
        Args:
            s3_url: Public S3 URL of the audio file (can be presigned)
            
        Returns:
            Audio file bytes
        """
        
        try:
            # Extract S3 key from URL
            # Expected formats include public and presigned URLs
            if not s3_url.startswith(f"https://{self.bucket_name}.s3."):
                raise S3Error(f"Invalid S3 URL format: {s3_url}")
            
            # Extract key from URL and strip query params if present
            url_parts = s3_url.split('/')
            s3_key_with_query = '/'.join(url_parts[3:])  # Everything after the domain
            s3_key = s3_key_with_query.split('?')[0]
            
            logger.info(f"Downloading audio from S3: {s3_key}")
            
            # Download from S3
            response = self.s3_client.get_object(
                Bucket=self.bucket_name,
                Key=s3_key
            )
            
            audio_data = response['Body'].read()
            
            logger.info(f"Successfully downloaded audio from S3: {len(audio_data)} bytes")
            
            return audio_data
            
        except ClientError as e:
            error_msg = f"Failed to download audio from S3: {str(e)}"
            logger.error(error_msg)
            raise S3Error(error_msg, bucket=self.bucket_name, key=s3_key)
        except Exception as e:
            error_msg = f"Unexpected error during S3 download: {str(e)}"
            logger.error(error_msg)
            raise S3Error(error_msg, bucket=self.bucket_name)
    
    async def delete_audio(self, s3_url: str) -> None:
        """
        Delete audio file from S3
        
        Args:
            s3_url: Public S3 URL of the audio file to delete (can be presigned)
        """
        
        try:
            # Extract S3 key from URL
            if not s3_url.startswith(f"https://{self.bucket_name}.s3."):
                raise S3Error(f"Invalid S3 URL format: {s3_url}")
            
            url_parts = s3_url.split('/')
            s3_key_with_query = '/'.join(url_parts[3:])
            s3_key = s3_key_with_query.split('?')[0]
            
            logger.info(f"Deleting audio from S3: {s3_key}")
            
            # Delete from S3
            self.s3_client.delete_object(
                Bucket=self.bucket_name,
                Key=s3_key
            )
            
            logger.info(f"Successfully deleted audio from S3: {s3_key}")
            
        except ClientError as e:
            error_msg = f"Failed to delete audio from S3: {str(e)}"
            logger.error(error_msg)
            raise S3Error(error_msg, bucket=self.bucket_name, key=s3_key)
        except Exception as e:
            error_msg = f"Unexpected error during S3 deletion: {str(e)}"
            logger.error(error_msg)
            raise S3Error(error_msg, bucket=self.bucket_name)
    
    async def cleanup_old_files(self, days_old: int = 7) -> int:
        """
        Clean up audio files older than specified days
        
        Args:
            days_old: Delete files older than this many days
            
        Returns:
            Number of files deleted
        """
        
        try:
            logger.info(f"Cleaning up S3 files older than {days_old} days")
            
            cutoff_date = datetime.utcnow() - timedelta(days=days_old)
            deleted_count = 0
            
            # List objects in the audio/ prefix
            paginator = self.s3_client.get_paginator('list_objects_v2')
            pages = paginator.paginate(Bucket=self.bucket_name, Prefix='audio/')
            
            objects_to_delete = []
            
            for page in pages:
                if 'Contents' not in page:
                    continue
                
                for obj in page['Contents']:
                    # Check if file is older than cutoff
                    if obj['LastModified'].replace(tzinfo=None) < cutoff_date:
                        objects_to_delete.append({'Key': obj['Key']})
            
            # Delete old files in batches
            if objects_to_delete:
                for i in range(0, len(objects_to_delete), 1000):  # S3 delete limit
                    batch = objects_to_delete[i:i+1000]
                    
                    self.s3_client.delete_objects(
                        Bucket=self.bucket_name,
                        Delete={'Objects': batch}
                    )
                    
                    deleted_count += len(batch)
            
            logger.info(f"Deleted {deleted_count} old audio files from S3")
            
            return deleted_count
            
        except ClientError as e:
            error_msg = f"Failed to cleanup old S3 files: {str(e)}"
            logger.error(error_msg)
            raise S3Error(error_msg, bucket=self.bucket_name)
        except Exception as e:
            error_msg = f"Unexpected error during S3 cleanup: {str(e)}"
            logger.error(error_msg)
            raise S3Error(error_msg, bucket=self.bucket_name)
    
    async def health_check(self) -> bool:
        """
        Perform a health check on the S3 connection
        
        Returns:
            True if healthy, False otherwise
        """
        
        try:
            # Simple head bucket operation
            self.s3_client.head_bucket(Bucket=self.bucket_name)
            logger.info("S3 health check passed")
            return True
            
        except Exception as e:
            logger.error(f"S3 health check failed: {str(e)}")
            return False
    
    def get_presigned_upload_url(
        self,
        user_id: str,
        file_extension: str = "mp3",
        content_type: str = "audio/mpeg",
        expiration: int = 3600
    ) -> tuple[str, str]:
        """
        Generate a presigned URL for direct upload to S3
        
        Args:
            user_id: User identifier
            file_extension: File extension
            content_type: MIME type
            expiration: URL expiration time in seconds
            
        Returns:
            Tuple of (presigned_url, s3_key)
        """
        
        try:
            s3_key = self._generate_audio_key(user_id, file_extension)
            
            presigned_url = self.s3_client.generate_presigned_url(
                'put_object',
                Params={
                    'Bucket': self.bucket_name,
                    'Key': s3_key,
                    'ContentType': content_type
                },
                ExpiresIn=expiration
            )
            
            logger.info(f"Generated presigned upload URL for key: {s3_key}")
            
            return presigned_url, s3_key
            
        except ClientError as e:
            error_msg = f"Failed to generate presigned URL: {str(e)}"
            logger.error(error_msg)
            raise S3Error(error_msg, bucket=self.bucket_name) 