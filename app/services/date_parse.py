"""
Robust date parsing service with timezone support
"""

import re
from datetime import datetime, timedelta
from typing import Optional, List, Tuple
import pytz
from dateutil import parser
from dateutil.relativedelta import relativedelta

from ..config import settings
from ..utils.errors import DateParsingError
from ..utils.logging import get_logger

logger = get_logger(__name__)


class DateParsingService:
    """Service for parsing natural language dates and date ranges"""
    
    def __init__(self):
        self.timezone = pytz.timezone(settings.app_timezone)
        self.utc = pytz.UTC
        
        # Month name mappings (English and common variations)
        self.month_names = {
            'january': 1, 'jan': 1,
            'february': 2, 'feb': 2,
            'march': 3, 'mar': 3,
            'april': 4, 'apr': 4,
            'may': 5,
            'june': 6, 'jun': 6,
            'july': 7, 'jul': 7,
            'august': 8, 'aug': 8,
            'september': 9, 'sep': 9, 'sept': 9,
            'october': 10, 'oct': 10,
            'november': 11, 'nov': 11,
            'december': 12, 'dec': 12
        }
        
        # Weekday mappings
        self.weekday_names = {
            'monday': 0, 'mon': 0,
            'tuesday': 1, 'tue': 1, 'tues': 1,
            'wednesday': 2, 'wed': 2,
            'thursday': 3, 'thu': 3, 'thur': 3, 'thurs': 3,
            'friday': 4, 'fri': 4,
            'saturday': 5, 'sat': 5,
            'sunday': 6, 'sun': 6
        }
    
    def get_current_time(self) -> datetime:
        """Get current time in the configured timezone"""
        return datetime.now(self.timezone)
    
    def to_date_string(self, dt: datetime) -> str:
        """Convert datetime to YYYY-MM-DD string"""
        return dt.strftime("%Y-%m-%d")
    
    def parse_relative_date(self, text: str) -> Optional[datetime]:
        """Parse relative dates like 'today', 'tomorrow', 'next week'"""
        
        text = text.lower().strip()
        current = self.get_current_time()
        
        if text in ['today']:
            return current
        elif text in ['tomorrow']:
            return current + timedelta(days=1)
        elif text in ['day after tomorrow']:
            return current + timedelta(days=2)
        elif text in ['yesterday']:
            return current - timedelta(days=1)
        elif text.startswith('next '):
            # Handle "next monday", "next week", etc.
            rest = text[5:]
            if rest == 'week':
                return current + timedelta(weeks=1)
            elif rest == 'month':
                return current + relativedelta(months=1)
            elif rest in self.weekday_names:
                target_weekday = self.weekday_names[rest]
                days_ahead = target_weekday - current.weekday()
                if days_ahead <= 0:  # Target day already happened this week
                    days_ahead += 7
                return current + timedelta(days=days_ahead)
        elif text.startswith('this '):
            # Handle "this friday", "this month", etc.
            rest = text[5:]
            if rest in self.weekday_names:
                target_weekday = self.weekday_names[rest]
                days_ahead = target_weekday - current.weekday()
                if days_ahead < 0:  # If the day has passed, assume next week
                    days_ahead += 7
                return current + timedelta(days=days_ahead)
        elif text.startswith('in '):
            # Handle "in 3 days", "in 2 weeks", etc.
            match = re.match(r'in (\d+) (day|days|week|weeks|month|months)', text)
            if match:
                number = int(match.group(1))
                unit = match.group(2)
                if unit.startswith('day'):
                    return current + timedelta(days=number)
                elif unit.startswith('week'):
                    return current + timedelta(weeks=number)
                elif unit.startswith('month'):
                    return current + relativedelta(months=number)
        
        return None
    
    def parse_numeric_date(self, text: str) -> Optional[datetime]:
        """Parse numeric dates like '24-08-2025', '24th August', etc."""
        
        text = text.lower().strip()
        current = self.get_current_time()
        
        # Pattern for "24th August", "24 Aug", etc.
        ordinal_pattern = r'(\d{1,2})(st|nd|rd|th)?\s+(january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)'
        match = re.search(ordinal_pattern, text)
        if match:
            day = int(match.group(1))
            month_name = match.group(3)
            month = self.month_names.get(month_name)
            
            if month:
                # Try current year first, then next year if date has passed
                year = current.year
                try:
                    date = current.replace(year=year, month=month, day=day)
                    if date < current:
                        date = date.replace(year=year + 1)
                    return date
                except ValueError:
                    # Invalid date (e.g., Feb 30th)
                    pass
        
        # Pattern for various date formats
        date_patterns = [
            r'(\d{1,2})[/-](\d{1,2})[/-](\d{4})',  # DD/MM/YYYY or DD-MM-YYYY
            r'(\d{4})[/-](\d{1,2})[/-](\d{1,2})',  # YYYY/MM/DD or YYYY-MM-DD
            r'(\d{1,2})[/-](\d{1,2})[/-](\d{2})',  # DD/MM/YY or DD-MM-YY
        ]
        
        for pattern in date_patterns:
            match = re.search(pattern, text)
            if match:
                try:
                    # Try to parse with dateutil
                    parsed_date = parser.parse(match.group(0), dayfirst=True)
                    # Convert to our timezone
                    if parsed_date.tzinfo is None:
                        parsed_date = self.timezone.localize(parsed_date)
                    else:
                        parsed_date = parsed_date.astimezone(self.timezone)
                    return parsed_date
                except (ValueError, parser.ParserError):
                    continue
        
        return None
    
    def parse_month_year(self, text: str) -> Optional[Tuple[int, int]]:
        """Parse month and year from text like 'September 2025', 'Sep 25'"""
        
        text = text.lower().strip()
        current = self.get_current_time()
        
        # Pattern for "September 2025", "Sep 25", etc.
        month_year_pattern = r'(january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)\s*(\d{2,4})?'
        
        match = re.search(month_year_pattern, text)
        if match:
            month_name = match.group(1)
            year_str = match.group(2)
            
            month = self.month_names.get(month_name)
            if month:
                if year_str:
                    year = int(year_str)
                    if year < 100:  # Two-digit year
                        year += 2000 if year < 50 else 1900
                else:
                    # No year specified, use current or next year
                    year = current.year
                    if month < current.month:
                        year += 1
                
                return month, year
        
        return None
    
    def parse_date_range(self, text: str) -> Optional[Tuple[datetime, datetime]]:
        """Parse date ranges like '12th-16th August', 'March 15-20'"""
        
        text = text.lower().strip()
        current = self.get_current_time()
        
        # Pattern for "12th-16th August", "15-20 March", etc.
        range_patterns = [
            r'(\d{1,2})(st|nd|rd|th)?[–\-](\d{1,2})(st|nd|rd|th)?\s+(january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)',
            r'(january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)\s+(\d{1,2})[–\-](\d{1,2})'
        ]
        
        for pattern in range_patterns:
            match = re.search(pattern, text)
            if match:
                groups = match.groups()
                
                if len(groups) >= 5:  # First pattern
                    start_day = int(groups[0])
                    end_day = int(groups[2])
                    month_name = groups[4]
                elif len(groups) >= 3:  # Second pattern
                    month_name = groups[0]
                    start_day = int(groups[1])
                    end_day = int(groups[2])
                else:
                    continue
                
                month = self.month_names.get(month_name)
                if month:
                    year = current.year
                    if month < current.month:
                        year += 1
                    
                    try:
                        start_date = current.replace(year=year, month=month, day=start_day)
                        end_date = current.replace(year=year, month=month, day=end_day)
                        
                        if start_date < current:
                            start_date = start_date.replace(year=year + 1)
                            end_date = end_date.replace(year=year + 1)
                        
                        return start_date, end_date
                    except ValueError:
                        continue
        
        return None
    
    def parse_date(self, text: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """
        Parse a date string and return normalized information
        
        Args:
            text: Natural language date string
            
        Returns:
            Tuple of (date_type, start_date, end_date) where:
            - date_type: 'exact', 'month', 'range'
            - start_date: Start date in YYYY-MM-DD format
            - end_date: End date in YYYY-MM-DD format (same as start for exact)
        """
        
        if not text or not text.strip():
            return None, None, None
        
        text = text.strip()
        
        try:
            # Try relative dates first
            parsed_date = self.parse_relative_date(text)
            if parsed_date:
                date_str = self.to_date_string(parsed_date)
                return 'exact', date_str, date_str
            
            # Try date ranges
            date_range = self.parse_date_range(text)
            if date_range:
                start_date, end_date = date_range
                return 'range', self.to_date_string(start_date), self.to_date_string(end_date)
            
            # Try month/year parsing for monthly searches
            month_year = self.parse_month_year(text)
            if month_year:
                month, year = month_year
                # Get first and last day of the month
                start_date = datetime(year, month, 1, tzinfo=self.timezone)
                if month == 12:
                    end_date = datetime(year + 1, 1, 1, tzinfo=self.timezone) - timedelta(days=1)
                else:
                    end_date = datetime(year, month + 1, 1, tzinfo=self.timezone) - timedelta(days=1)
                
                return 'month', self.to_date_string(start_date), self.to_date_string(end_date)
            
            # Try numeric date parsing
            parsed_date = self.parse_numeric_date(text)
            if parsed_date:
                date_str = self.to_date_string(parsed_date)
                return 'exact', date_str, date_str
            
            # Try dateutil as fallback
            try:
                parsed_date = parser.parse(text, dayfirst=True)
                if parsed_date.tzinfo is None:
                    parsed_date = self.timezone.localize(parsed_date)
                else:
                    parsed_date = parsed_date.astimezone(self.timezone)
                
                # If parsed date is in the past, assume next year
                current = self.get_current_time()
                if parsed_date < current:
                    parsed_date = parsed_date.replace(year=current.year + 1)
                
                date_str = self.to_date_string(parsed_date)
                return 'exact', date_str, date_str
                
            except (ValueError, parser.ParserError):
                pass
            
            logger.warning(f"Could not parse date: {text}")
            return None, None, None
            
        except Exception as e:
            logger.error(f"Error parsing date '{text}': {str(e)}")
            raise DateParsingError(f"Failed to parse date: {text}", date_input=text)
    
    def expand_date_range(self, start_date: str, end_date: str) -> List[str]:
        """
        Expand a date range into individual dates
        
        Args:
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
            
        Returns:
            List of dates in YYYY-MM-DD format
        """
        
        try:
            start = datetime.strptime(start_date, "%Y-%m-%d")
            end = datetime.strptime(end_date, "%Y-%m-%d")
            
            dates = []
            current = start
            
            while current <= end:
                dates.append(current.strftime("%Y-%m-%d"))
                current += timedelta(days=1)
            
            return dates
            
        except ValueError as e:
            logger.error(f"Error expanding date range {start_date} to {end_date}: {str(e)}")
            raise DateParsingError(f"Invalid date range: {start_date} to {end_date}")
    
    def get_month_dates(self, month: int, year: int, exclude_past: bool = True) -> List[str]:
        """
        Get all dates in a specific month
        
        Args:
            month: Month number (1-12)
            year: Year
            exclude_past: Whether to exclude dates in the past
            
        Returns:
            List of dates in YYYY-MM-DD format
        """
        
        try:
            current = self.get_current_time() if exclude_past else None
            
            # First day of the month
            start_date = datetime(year, month, 1, tzinfo=self.timezone)
            
            # Last day of the month
            if month == 12:
                end_date = datetime(year + 1, 1, 1, tzinfo=self.timezone) - timedelta(days=1)
            else:
                end_date = datetime(year, month + 1, 1, tzinfo=self.timezone) - timedelta(days=1)
            
            dates = []
            current_date = start_date
            
            while current_date <= end_date:
                if not exclude_past or current_date >= current:
                    dates.append(self.to_date_string(current_date))
                current_date += timedelta(days=1)
            
            return dates
            
        except ValueError as e:
            logger.error(f"Error getting month dates for {month}/{year}: {str(e)}")
            raise DateParsingError(f"Invalid month/year: {month}/{year}")
    
    def is_valid_travel_date(self, date_str: str, min_advance_days: int = 1) -> bool:
        """
        Check if a date is valid for travel booking
        
        Args:
            date_str: Date in YYYY-MM-DD format
            min_advance_days: Minimum days in advance required
            
        Returns:
            True if date is valid for travel
        """
        
        try:
            date = datetime.strptime(date_str, "%Y-%m-%d")
            date = self.timezone.localize(date)
            current = self.get_current_time()
            
            min_date = current + timedelta(days=min_advance_days)
            
            return date >= min_date
            
        except ValueError:
            return False 