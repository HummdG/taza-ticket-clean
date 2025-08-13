#!/usr/bin/env python3
"""
Test script to verify the LogContext fix for the user_id overwrite issue
"""

import sys
import os

# Add the app directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

from app.utils.logging import LogContext, get_logger, setup_logging

def test_nested_log_context():
    """Test that nested LogContext with same user_id doesn't cause errors"""
    
    # Setup logging
    setup_logging("INFO")
    logger = get_logger("test_logger")
    
    try:
        # First LogContext with user_id
        with LogContext(message_sid="test_msg_1", user_id="whatsapp:+447948623631"):
            logger.info("First log message")
            
            # Nested LogContext with same user_id (this was causing the error)
            with LogContext(message_sid="test_msg_2", user_id="whatsapp:+447948623631"):
                logger.info("Second log message in nested context")
                
            logger.info("Back to first context")
        
        logger.info("Outside all contexts")
        
        print("✅ SUCCESS: Nested LogContext with same user_id works correctly!")
        return True
        
    except Exception as e:
        print(f"❌ ERROR: {str(e)}")
        return False

def test_nested_log_context_different_values():
    """Test nested LogContext with different user_id values"""
    
    setup_logging("INFO")
    logger = get_logger("test_logger_2")
    
    try:
        # First LogContext with user_id
        with LogContext(message_sid="test_msg_3", user_id="user1"):
            logger.info("First log message")
            
            # Nested LogContext with different user_id
            with LogContext(message_sid="test_msg_4", user_id="user2"):
                logger.info("Second log message with different user_id")
                
            logger.info("Back to first context")
        
        print("✅ SUCCESS: Nested LogContext with different user_id works correctly!")
        return True
        
    except Exception as e:
        print(f"❌ ERROR: {str(e)}")
        return False

if __name__ == "__main__":
    print("Testing LogContext fix...")
    
    # Test 1: Same user_id in nested contexts
    result1 = test_nested_log_context()
    
    # Test 2: Different user_id in nested contexts  
    result2 = test_nested_log_context_different_values()
    
    if result1 and result2:
        print("\n🎉 All tests passed! The LogContext fix is working correctly.")
        sys.exit(0)
    else:
        print("\n💥 Some tests failed. The LogContext fix needs more work.")
        sys.exit(1) 