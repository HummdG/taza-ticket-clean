"""
DynamoDB repository for conversation state and history management
"""

import json
from datetime import datetime
from typing import Optional, List, Dict, Any
from decimal import Decimal
import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

from ..config import settings
from ..models.schemas import ConversationData, Message, Slots, ConversationState, MessageModality
from ..utils.errors import DynamoDBError
from ..utils.logging import get_logger

logger = get_logger(__name__)


class DynamoDBRepository:
    """DynamoDB repository for conversation data management"""
    
    def __init__(self):
        self.dynamodb = boto3.resource(
            'dynamodb',
            region_name=settings.aws_region,
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key
        )
        self.table = self.dynamodb.Table(settings.dynamodb_table_name)
    
    def _decimal_to_float(self, obj):
        """Convert Decimal objects to float for JSON serialization"""
        if isinstance(obj, Decimal):
            return float(obj)
        elif isinstance(obj, dict):
            return {k: self._decimal_to_float(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._decimal_to_float(v) for v in obj]
        return obj
    
    def _float_to_decimal(self, obj):
        """Convert float objects to Decimal for DynamoDB storage"""
        if isinstance(obj, float):
            return Decimal(str(obj))
        elif isinstance(obj, dict):
            return {k: self._float_to_decimal(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._float_to_decimal(v) for v in obj]
        return obj
    
    def _serialize_conversation_data(self, conversation_data: ConversationData) -> Dict[str, Any]:
        """Serialize ConversationData for DynamoDB storage"""
        
        # Convert to dict
        data = conversation_data.dict()
        
        # Convert floats to Decimals for DynamoDB
        data = self._float_to_decimal(data)
        
        # Convert datetime objects to ISO strings
        data['created_at'] = conversation_data.created_at.isoformat()
        data['updated_at'] = conversation_data.updated_at.isoformat()
        
        # Convert message timestamps
        for message in data['messages']:
            message['timestamp'] = message['timestamp'] if isinstance(message['timestamp'], str) else message['timestamp'].isoformat()
        
        return data
    
    def _deserialize_conversation_data(self, item: Dict[str, Any]) -> ConversationData:
        """Deserialize DynamoDB item to ConversationData"""
        
        # Convert Decimals to floats
        item = self._decimal_to_float(item)
        
        # Convert ISO strings back to datetime objects
        if 'created_at' in item and isinstance(item['created_at'], str):
            item['created_at'] = datetime.fromisoformat(item['created_at'])
        
        if 'updated_at' in item and isinstance(item['updated_at'], str):
            item['updated_at'] = datetime.fromisoformat(item['updated_at'])
        
        # Convert message timestamps
        for message in item.get('messages', []):
            if 'timestamp' in message and isinstance(message['timestamp'], str):
                message['timestamp'] = datetime.fromisoformat(message['timestamp'])
        
        # Ensure required fields exist with defaults
        if 'slots' not in item or item['slots'] is None:
            from ..models.schemas import Slots
            item['slots'] = Slots().dict()
        
        if 'messages' not in item or item['messages'] is None:
            item['messages'] = []
        
        # Remove DynamoDB-specific keys that shouldn't be in ConversationData
        item_clean = {k: v for k, v in item.items() if k not in ['user_id', 'sort_key']}
        
        # Re-add user_id as it's needed
        item_clean['user_id'] = item['user_id']
        
        return ConversationData(**item_clean)
    
    async def get_conversation(self, user_id: str) -> Optional[ConversationData]:
        """
        Get the latest conversation state for a user
        
        Args:
            user_id: User identifier
            
        Returns:
            ConversationData if found, None otherwise
        """
        
        try:
            logger.info(f"Retrieving conversation for user: {user_id}")
            
            # First try to read a stable 'CURRENT' record (if present)
            try:
                current_item_resp = self.table.get_item(
                    Key={'user_id': user_id, 'sort_key': 'CURRENT'},
                    ConsistentRead=True
                )
                current_item = current_item_resp.get('Item')
                if current_item:
                    conversation_data = self._deserialize_conversation_data(current_item)
                    logger.info(f"Retrieved conversation for user: {user_id}, {len(conversation_data.messages)} messages")
                    return conversation_data
            except Exception:
                # Fall back to query
                pass
            
            # Query for the latest conversation entry for this user
            response = self.table.query(
                KeyConditionExpression=Key('user_id').eq(user_id),
                ScanIndexForward=False,  # Sort in descending order (latest first)
                Limit=1
            )
            
            items = response.get('Items', [])
            if not items:
                logger.info(f"No conversation found for user: {user_id}")
                return None
            
            conversation_data = self._deserialize_conversation_data(items[0])
            logger.info(f"Retrieved conversation for user: {user_id}, {len(conversation_data.messages)} messages")
            
            return conversation_data
            
        except ClientError as e:
            error_msg = f"Failed to retrieve conversation for user {user_id}: {str(e)}"
            logger.error(error_msg)
            raise DynamoDBError(error_msg)
    
    async def save_conversation(self, conversation_data: ConversationData) -> None:
        """
        Save conversation state to DynamoDB
        
        Args:
            conversation_data: Conversation data to save
        """
        
        try:
            logger.info(f"Saving conversation for user: {conversation_data.user_id}")
            
            # Update the updated_at timestamp
            conversation_data.updated_at = datetime.utcnow()
            
            # Serialize for DynamoDB
            item = self._serialize_conversation_data(conversation_data)
            
            # Add DynamoDB keys to match table schema (versioned record)
            item['user_id'] = conversation_data.user_id  # Partition key
            item['sort_key'] = conversation_data.updated_at.isoformat()  # Sort key
            
            # Save versioned record
            self.table.put_item(Item=item)
            
            # Also save/overwrite a stable 'CURRENT' pointer for fast reads
            current_item = dict(item)
            current_item['sort_key'] = 'CURRENT'
            self.table.put_item(Item=current_item)
            
            logger.info(f"Saved conversation for user: {conversation_data.user_id}")
            
        except ClientError as e:
            error_msg = f"Failed to save conversation for user {conversation_data.user_id}: {str(e)}"
            logger.error(error_msg)
            raise DynamoDBError(error_msg)
    
    async def append_message(self, user_id: str, message: Message) -> ConversationData:
        """
        Append a message to the conversation history
        
        Args:
            user_id: User identifier
            message: Message to append
            
        Returns:
            Updated conversation data
        """
        
        try:
            # Get existing conversation or create new one
            conversation_data = await self.get_conversation(user_id)
            
            if conversation_data is None:
                # Create new conversation
                conversation_data = ConversationData(
                    user_id=user_id,
                    slots=Slots(),
                    messages=[],
                    state=ConversationState.INITIAL
                )
            
            # Append the new message
            conversation_data.messages.append(message)
            
            # Update modality and language tracking
            conversation_data.last_modality = message.modality
            if message.language:
                conversation_data.language = message.language
            
            # Save updated conversation
            await self.save_conversation(conversation_data)
            
            logger.info(f"Appended message for user: {user_id}, total messages: {len(conversation_data.messages)}")
            
            return conversation_data
            
        except Exception as e:
            error_msg = f"Failed to append message for user {user_id}: {str(e)}"
            logger.error(error_msg)
            raise DynamoDBError(error_msg)
    
    async def update_slots(self, user_id: str, slots: Slots) -> ConversationData:
        """
        Update conversation slots
        
        Args:
            user_id: User identifier
            slots: Updated slots data
            
        Returns:
            Updated conversation data
        """
        
        try:
            # Get existing conversation
            conversation_data = await self.get_conversation(user_id)
            
            if conversation_data is None:
                # Create new conversation
                conversation_data = ConversationData(
                    user_id=user_id,
                    slots=slots,
                    messages=[],
                    state=ConversationState.COLLECTING_SLOTS
                )
            else:
                # Update existing slots
                conversation_data.slots = slots
                conversation_data.state = ConversationState.COLLECTING_SLOTS
            
            # Save updated conversation
            await self.save_conversation(conversation_data)
            
            logger.info(f"Updated slots for user: {user_id}")
            
            return conversation_data
            
        except Exception as e:
            error_msg = f"Failed to update slots for user {user_id}: {str(e)}"
            logger.error(error_msg)
            raise DynamoDBError(error_msg)
    
    async def update_state(
        self, 
        user_id: str, 
        state: ConversationState,
        search_hash: Optional[str] = None,
        itinerary_summary: Optional[str] = None
    ) -> ConversationData:
        """
        Update conversation state
        
        Args:
            user_id: User identifier
            state: New conversation state
            search_hash: Optional search parameters hash
            itinerary_summary: Optional itinerary summary
            
        Returns:
            Updated conversation data
        """
        
        try:
            # Get existing conversation
            conversation_data = await self.get_conversation(user_id)
            
            if conversation_data is None:
                raise DynamoDBError(f"No conversation found for user {user_id}")
            
            # Update state
            conversation_data.state = state
            
            if search_hash:
                conversation_data.last_completed_search = search_hash
            
            if itinerary_summary:
                conversation_data.last_itinerary_summary = itinerary_summary
            
            # Save updated conversation
            await self.save_conversation(conversation_data)
            
            logger.info(f"Updated state for user: {user_id} to {state}")
            
            return conversation_data
            
        except Exception as e:
            error_msg = f"Failed to update state for user {user_id}: {str(e)}"
            logger.error(error_msg)
            raise DynamoDBError(error_msg)
    
    async def get_conversation_history(
        self, 
        user_id: str, 
        limit: int = 10
    ) -> List[ConversationData]:
        """
        Get conversation history for a user
        
        Args:
            user_id: User identifier
            limit: Maximum number of conversation entries to retrieve
            
        Returns:
            List of conversation data entries
        """
        
        try:
            logger.info(f"Retrieving conversation history for user: {user_id}, limit: {limit}")
            
            response = self.table.query(
                KeyConditionExpression=Key('user_id').eq(user_id),
                ScanIndexForward=False,  # Sort in descending order (latest first)
                Limit=limit
            )
            
            items = response.get('Items', [])
            conversations = []
            
            for item in items:
                conversation_data = self._deserialize_conversation_data(item)
                conversations.append(conversation_data)
            
            logger.info(f"Retrieved {len(conversations)} conversation entries for user: {user_id}")
            
            return conversations
            
        except ClientError as e:
            error_msg = f"Failed to retrieve conversation history for user {user_id}: {str(e)}"
            logger.error(error_msg)
            raise DynamoDBError(error_msg)
    
    async def delete_conversation(self, user_id: str) -> None:
        """
        Delete all conversation data for a user
        
        Args:
            user_id: User identifier
        """
        
        try:
            logger.info(f"Deleting conversation data for user: {user_id}")
            
            # Get all entries for this user
            response = self.table.query(
                KeyConditionExpression=Key('user_id').eq(user_id)
            )
            
            items = response.get('Items', [])
            
            # Delete all entries
            with self.table.batch_writer() as batch:
                for item in items:
                    batch.delete_item(
                        Key={
                            'user_id': item['user_id'],
                            'sort_key': item['sort_key']
                        }
                    )
            
            logger.info(f"Deleted {len(items)} conversation entries for user: {user_id}")
            
        except ClientError as e:
            error_msg = f"Failed to delete conversation for user {user_id}: {str(e)}"
            logger.error(error_msg)
            raise DynamoDBError(error_msg)
    
    async def health_check(self) -> bool:
        """
        Perform a health check on the DynamoDB connection
        
        Returns:
            True if healthy, False otherwise
        """
        
        try:
            # Simple describe table operation
            self.table.load()
            logger.info("DynamoDB health check passed")
            return True
            
        except Exception as e:
            logger.error(f"DynamoDB health check failed: {str(e)}")
            return False 