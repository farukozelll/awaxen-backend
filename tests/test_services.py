"""
Service Tests.

Test business logic services.
"""
import pytest
from unittest.mock import Mock, patch
from datetime import datetime, timezone

from app.services.automation_engine import AutomationEngine, automation_engine
from app.models import Automation, MarketPrice


class TestAutomationEngine:
    """AutomationEngine tests."""
    
    def test_evaluate_price_trigger_below_threshold(self, db_session, sample_automation):
        """Test price trigger when price is below threshold."""
        # Create a market price below the threshold (2.0)
        price = MarketPrice(
            time=datetime.now(timezone.utc),
            price=1.5,
            ptf=1500.0
        )
        db_session.add(price)
        db_session.commit()
        
        engine = AutomationEngine()
        should_trigger, reason = engine.evaluate(sample_automation)
        
        assert should_trigger is True
        assert "1.50" in reason
    
    def test_evaluate_price_trigger_above_threshold(self, db_session, sample_automation):
        """Test price trigger when price is above threshold."""
        # Create a market price above the threshold (2.0)
        price = MarketPrice(
            time=datetime.now(timezone.utc),
            price=3.0,
            ptf=3000.0
        )
        db_session.add(price)
        db_session.commit()
        
        engine = AutomationEngine()
        should_trigger, reason = engine.evaluate(sample_automation)
        
        assert should_trigger is False
    
    def test_evaluate_time_trigger(self, db_session, sample_organization, sample_user):
        """Test time-based trigger."""
        automation = Automation(
            organization_id=sample_organization.id,
            created_by=sample_user.id,
            name="Time Automation",
            rules={
                "trigger": {
                    "type": "time_range",
                    "start": "00:00",
                    "end": "23:59",
                    "days": [0, 1, 2, 3, 4, 5, 6]
                },
                "action": {"type": "turn_on"}
            }
        )
        db_session.add(automation)
        db_session.commit()
        
        engine = AutomationEngine()
        should_trigger, reason = engine.evaluate(automation)
        
        # Should always trigger since we're within 00:00-23:59
        assert should_trigger is True
    
    def test_evaluate_always_trigger(self, db_session, sample_organization, sample_user):
        """Test always trigger type."""
        automation = Automation(
            organization_id=sample_organization.id,
            created_by=sample_user.id,
            name="Always Trigger",
            rules={
                "trigger": {"type": "always"},
                "action": {"type": "turn_on"}
            }
        )
        db_session.add(automation)
        db_session.commit()
        
        engine = AutomationEngine()
        should_trigger, reason = engine.evaluate(automation)
        
        # Always trigger should return True
        assert should_trigger is True
    
    def test_run_automation_success(self, db_session, sample_automation):
        """Test running automation successfully."""
        # Add market price to trigger
        price = MarketPrice(
            time=datetime.now(timezone.utc),
            price=1.0,
            ptf=1000.0
        )
        db_session.add(price)
        db_session.commit()
        
        engine = AutomationEngine()
        
        # Mock the execute method to avoid actual device control
        with patch.object(engine, 'execute', return_value=True):
            result = engine.run_automation(sample_automation)
        
        assert result['triggered'] is True
        assert result['executed'] is True


class TestAutomationEngineEdgeCases:
    """Edge case tests for AutomationEngine."""
    
    def test_no_price_data(self, db_session, sample_automation):
        """Test behavior when no price data exists."""
        # Ensure no price data
        MarketPrice.query.delete()
        db_session.commit()
        
        engine = AutomationEngine()
        should_trigger, reason = engine.evaluate(sample_automation)
        
        assert should_trigger is False
        assert "No price data" in reason
    
    def test_automation_without_asset(self, db_session, sample_organization, sample_user):
        """Test automation without linked asset."""
        automation = Automation(
            organization_id=sample_organization.id,
            created_by=sample_user.id,
            name="No Asset Automation",
            asset_id=None,
            rules={
                "trigger": {"type": "always"},
                "action": {"type": "turn_on"}
            }
        )
        db_session.add(automation)
        db_session.commit()
        
        engine = AutomationEngine()
        result = engine.execute(automation)
        
        # Should fail because no asset
        assert result is False
