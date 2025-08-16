"""
Enhanced CRUD operations for trigger management with validation and testing.
"""

import asyncio
import json
import os
import smtplib
from datetime import UTC, datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.trigger import EmailTrigger, Trigger, WebhookTrigger
from ..schemas.trigger import (
    EmailTriggerBase,
    TriggerCreate,
    TriggerCreateInternal,
    TriggerDelete,
    TriggerFilter,
    TriggerRead,
    TriggerSort,
    TriggerTestRequest,
    TriggerTestResult,
    TriggerUpdate,
    TriggerUpdateInternal,
    TriggerValidationRequest,
    TriggerValidationResult,
    WebhookTriggerBase,
)
from .base import EnhancedCRUD


class CRUDTrigger(
    EnhancedCRUD[
        Trigger,
        TriggerCreateInternal,
        TriggerUpdate,
        TriggerUpdateInternal,
        TriggerDelete,
        TriggerRead,
        TriggerFilter,
        TriggerSort
    ]
):
    """
    Enhanced CRUD operations for Trigger model with validation and testing.
    Supports both email and webhook triggers with credential management.
    """

    async def create_with_config(
        self,
        db: AsyncSession,
        obj_in: TriggerCreate
    ) -> TriggerRead:
        """
        Create trigger with email or webhook configuration.

        Args:
            db: Database session
            obj_in: Trigger creation data

        Returns:
            Created trigger
        """
        # Create main trigger
        trigger_data = TriggerCreateInternal(**obj_in.model_dump(
            exclude={"email_config", "webhook_config"}
        ))
        trigger = Trigger(**trigger_data.model_dump())
        db.add(trigger)
        await db.flush()

        # Create type-specific configuration
        if obj_in.trigger_type == "email" and obj_in.email_config:
            email_config = EmailTrigger(
                trigger_id=trigger.id,
                **obj_in.email_config.model_dump()
            )
            db.add(email_config)
        elif obj_in.trigger_type == "webhook" and obj_in.webhook_config:
            webhook_config = WebhookTrigger(
                trigger_id=trigger.id,
                **obj_in.webhook_config.model_dump()
            )
            db.add(webhook_config)

        await db.flush()
        await db.refresh(trigger)

        result = await self._get_trigger_with_config(db, trigger.id)
        if not result:
            raise ValueError("Failed to retrieve created trigger")
        return result

    async def update_with_config(
        self,
        db: AsyncSession,
        trigger_id: Any,
        obj_in: TriggerUpdate,
        tenant_id: Any
    ) -> Optional[TriggerRead]:
        """
        Update trigger including configuration.

        Args:
            db: Database session
            trigger_id: Trigger ID
            obj_in: Update data
            tenant_id: Tenant ID for security

        Returns:
            Updated trigger or None
        """
        # Get trigger
        query = select(Trigger).where(
            Trigger.id == trigger_id,
            Trigger.tenant_id == tenant_id
        )
        result = await db.execute(query)
        trigger = result.scalar_one_or_none()

        if not trigger:
            return None

        # Update main trigger fields
        update_dict = obj_in.model_dump(
            exclude={"email_config", "webhook_config"},
            exclude_unset=True
        )
        for key, value in update_dict.items():
            setattr(trigger, key, value)

        trigger.updated_at = datetime.now(UTC)

        # Update type-specific configuration
        if obj_in.email_config and trigger.trigger_type == "email":
            email_query = select(EmailTrigger).where(
                EmailTrigger.trigger_id == trigger_id
            )
            email_result = await db.execute(email_query)
            email_config = email_result.scalar_one_or_none()

            if email_config:
                for key, value in obj_in.email_config.model_dump(exclude_unset=True).items():
                    setattr(email_config, key, value)
                email_config.updated_at = datetime.now(UTC)

        elif obj_in.webhook_config and trigger.trigger_type == "webhook":
            webhook_query = select(WebhookTrigger).where(
                WebhookTrigger.trigger_id == trigger_id
            )
            webhook_result = await db.execute(webhook_query)
            webhook_config = webhook_result.scalar_one_or_none()

            if webhook_config:
                for key, value in obj_in.webhook_config.model_dump(exclude_unset=True).items():
                    setattr(webhook_config, key, value)
                webhook_config.updated_at = datetime.now(UTC)

        await db.flush()
        return await self._get_trigger_with_config(db, trigger_id)

    async def validate_trigger(
        self,
        db: AsyncSession,
        validation_request: TriggerValidationRequest
    ) -> TriggerValidationResult:
        """
        Validate trigger configuration and test connectivity.

        Args:
            db: Database session
            validation_request: Validation request

        Returns:
            Validation result
        """
        errors: list[str] = []
        warnings: list[str] = []

        # Get trigger with config
        trigger = await self._get_trigger_with_config(
            db,
            validation_request.trigger_id
        )

        if not trigger:
            errors.append("Trigger not found")
            return TriggerValidationResult(
                trigger_id=validation_request.trigger_id,
                is_valid=False,
                errors=errors,
                warnings=warnings
            )

        # Validate based on type
        if trigger.trigger_type == "email":
            if not trigger.email_config:
                errors.append("Email trigger missing configuration")
            elif validation_request.test_connection:
                # Test SMTP connection
                smtp_result = await self._test_smtp_connection(
                    trigger.email_config
                )
                if not smtp_result["success"]:
                    errors.append(
                        f"SMTP connection failed: {smtp_result['error']}")

        elif trigger.trigger_type == "webhook":
            if not trigger.webhook_config:
                errors.append("Webhook trigger missing configuration")
            elif validation_request.test_connection:
                # Test webhook URL
                webhook_result = await self._test_webhook_url(
                    trigger.webhook_config
                )
                if not webhook_result["success"]:
                    errors.append(
                        f"Webhook test failed: {webhook_result['error']}")

        # Update trigger validation status
        update_query = select(Trigger).where(
            Trigger.id == validation_request.trigger_id)
        result = await db.execute(update_query)
        trigger_obj = result.scalar_one_or_none()

        if trigger_obj:
            trigger_obj.validated = len(errors) == 0
            trigger_obj.validation_errors = {
                "errors": errors,
                "warnings": warnings
            }
            trigger_obj.last_validated_at = datetime.now(UTC)
            await db.flush()

        return TriggerValidationResult(
            trigger_id=validation_request.trigger_id,
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings
        )

    async def test_trigger(
        self,
        db: AsyncSession,
        test_request: TriggerTestRequest
    ) -> TriggerTestResult:
        """
        Test trigger with sample data.

        Args:
            db: Database session
            test_request: Test request

        Returns:
            Test result
        """
        start_time = datetime.now(UTC)
        success = False
        response = None
        error = None

        # Get trigger with config
        trigger = await self._get_trigger_with_config(
            db,
            test_request.trigger_id
        )

        if not trigger:
            error = "Trigger not found"
        elif trigger.trigger_type == "email" and trigger.email_config:
            # Test email trigger
            result = await self._send_test_email(
                trigger.email_config,
                test_request.test_data
            )
            success = result["success"]
            response = result.get("response")
            error = result.get("error")

        elif trigger.trigger_type == "webhook" and trigger.webhook_config:
            # Test webhook trigger
            result = await self._send_test_webhook(
                trigger.webhook_config,
                test_request.test_data
            )
            success = result["success"]
            response = result.get("response")
            error = result.get("error")
        else:
            error = "Invalid trigger configuration"

        # Calculate duration
        duration_ms = int(
            (datetime.now(UTC) - start_time).total_seconds() * 1000)

        return TriggerTestResult(
            trigger_id=test_request.trigger_id,
            success=success,
            response=response,
            error=error,
            duration_ms=duration_ms
        )

    async def get_active_triggers_by_type(
        self,
        db: AsyncSession,
        trigger_type: str,
        tenant_id: Optional[Any] = None
    ) -> list[TriggerRead]:
        """
        Get all active triggers of a specific type.

        Args:
            db: Database session
            trigger_type: Trigger type (email or webhook)
            tenant_id: Optional tenant filter

        Returns:
            List of active triggers
        """
        query = select(Trigger).where(
            Trigger.trigger_type == trigger_type,
            Trigger.active == True,  # noqa: E712
            Trigger.validated == True  # noqa: E712
        )

        if tenant_id:
            query = query.where(Trigger.tenant_id == tenant_id)

        result = await db.execute(query)
        triggers = result.scalars().all()

        results = []
        for trigger in triggers:
            trigger_read = await self._get_trigger_with_config(db, trigger.id)
            if trigger_read:
                results.append(trigger_read)

        return results

    async def activate_trigger(
        self,
        db: AsyncSession,
        trigger_id: Any,
        tenant_id: Any
    ) -> Optional[TriggerRead]:
        """
        Activate a trigger.

        Args:
            db: Database session
            trigger_id: Trigger ID
            tenant_id: Tenant ID

        Returns:
            Updated trigger or None
        """
        update_data = TriggerUpdate(
            name=None,
            slug=None,
            active=True
        )
        return await self.update_with_config(
            db,
            trigger_id,
            update_data,
            tenant_id
        )

    async def deactivate_trigger(
        self,
        db: AsyncSession,
        trigger_id: Any,
        tenant_id: Any
    ) -> Optional[TriggerRead]:
        """
        Deactivate a trigger.

        Args:
            db: Database session
            trigger_id: Trigger ID
            tenant_id: Tenant ID

        Returns:
            Updated trigger or None
        """
        update_data = TriggerUpdate(
            name=None,
            slug=None,
            active=False
        )
        return await self.update_with_config(
            db,
            trigger_id,
            update_data,
            tenant_id
        )

    async def get_by_slug(
        self,
        db: AsyncSession,
        slug: str,
        tenant_id: Any
    ) -> Optional[Trigger]:
        """
        Get trigger by slug within tenant context.

        Args:
            db: Database session
            slug: Trigger slug
            tenant_id: Tenant ID for multi-tenant isolation

        Returns:
            Trigger if found and authorized, None otherwise
        """
        query = select(Trigger).where(
            Trigger.slug == slug,
            Trigger.tenant_id == tenant_id
        )
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def bulk_validate(
        self,
        db: AsyncSession,
        trigger_ids: list[Any]
    ) -> dict[str, TriggerValidationResult]:
        """
        Validate multiple triggers in parallel.

        Args:
            db: Database session
            trigger_ids: List of trigger IDs

        Returns:
            Dictionary of validation results
        """
        tasks = []
        for trigger_id in trigger_ids:
            request = TriggerValidationRequest(
                trigger_id=trigger_id,
                test_connection=True
            )
            tasks.append(self.validate_trigger(db, request))

        results = await asyncio.gather(*tasks)

        return {
            str(trigger_ids[i]): results[i]
            for i in range(len(trigger_ids))
        }

    # Private helper methods

    async def _get_trigger_with_config(
        self,
        db: AsyncSession,
        trigger_id: Any
    ) -> Optional[TriggerRead]:
        """
        Get trigger with its configuration.

        Args:
            db: Database session
            trigger_id: Trigger ID

        Returns:
            Trigger with config or None
        """
        query = select(Trigger).where(Trigger.id == trigger_id)
        result = await db.execute(query)
        trigger = result.scalar_one_or_none()

        if not trigger:
            return None

        trigger_dict = TriggerRead.model_validate(trigger).model_dump()

        # Get type-specific config
        if trigger.trigger_type == "email":
            email_query = select(EmailTrigger).where(
                EmailTrigger.trigger_id == trigger_id
            )
            email_result = await db.execute(email_query)
            email_config = email_result.scalar_one_or_none()
            if email_config:
                trigger_dict["email_config"] = email_config

        elif trigger.trigger_type == "webhook":
            webhook_query = select(WebhookTrigger).where(
                WebhookTrigger.trigger_id == trigger_id
            )
            webhook_result = await db.execute(webhook_query)
            webhook_config = webhook_result.scalar_one_or_none()
            if webhook_config:
                trigger_dict["webhook_config"] = webhook_config

        return TriggerRead(**trigger_dict)

    def _get_credential_value(
        self,
        credential_type: str,
        credential_value: str
    ) -> str:
        """
        Get actual credential value based on storage type.

        Args:
            credential_type: Storage type (Plain, Environment, HashicorpCloudVault)
            credential_value: Stored value or reference

        Returns:
            Actual credential value
        """
        if credential_type == "Plain":
            return credential_value
        elif credential_type == "Environment":
            return os.getenv(credential_value, "")
        elif credential_type == "HashicorpCloudVault":
            # TODO: Implement Vault integration
            return ""
        return credential_value

    async def _test_smtp_connection(
        self,
        email_config: EmailTriggerBase
    ) -> dict[str, Any]:
        """
        Test SMTP connection.

        Args:
            email_config: Email configuration

        Returns:
            Test result dictionary
        """
        try:
            username = self._get_credential_value(
                email_config.username_type,
                email_config.username_value
            )
            password = self._get_credential_value(
                email_config.password_type,
                email_config.password_value
            )

            # Connect to SMTP server
            with smtplib.SMTP_SSL(email_config.host, email_config.port, timeout=5) as server:
                server.login(username, password)

            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _test_webhook_url(
        self,
        webhook_config: WebhookTriggerBase
    ) -> dict[str, Any]:
        """
        Test webhook URL connectivity.

        Args:
            webhook_config: Webhook configuration

        Returns:
            Test result dictionary
        """
        try:
            url = self._get_credential_value(
                webhook_config.url_type,
                webhook_config.url_value
            )

            async with httpx.AsyncClient(timeout=5.0) as client:
                # Send test request based on method
                if webhook_config.method == "GET":
                    response = await client.get(url, headers=webhook_config.headers)
                else:
                    response = await client.request(
                        webhook_config.method,
                        url,
                        headers=webhook_config.headers,
                        json={"test": True}
                    )

                response.raise_for_status()

            return {"success": True, "response": {"status_code": response.status_code}}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _send_test_email(
        self,
        email_config: EmailTriggerBase,
        test_data: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Send test email.

        Args:
            email_config: Email configuration
            test_data: Test data to include

        Returns:
            Result dictionary
        """
        try:
            username = self._get_credential_value(
                email_config.username_type,
                email_config.username_value
            )
            password = self._get_credential_value(
                email_config.password_type,
                email_config.password_value
            )

            # Create message
            msg = MIMEMultipart()
            msg['From'] = email_config.sender
            # Test with first recipient
            msg['To'] = ', '.join(email_config.recipients[:1])
            msg['Subject'] = f"[TEST] {email_config.message_title}"

            # Add body
            body = f"{email_config.message_body}\n\nTest Data:\n{json.dumps(test_data, indent=2)}"
            msg.attach(MIMEText(body, 'plain'))

            # Send email
            with smtplib.SMTP_SSL(email_config.host, email_config.port, timeout=10) as server:
                server.login(username, password)
                server.send_message(msg)

            return {"success": True, "response": {"recipients": email_config.recipients[:1]}}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _send_test_webhook(
        self,
        webhook_config: WebhookTriggerBase,
        test_data: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Send test webhook.

        Args:
            webhook_config: Webhook configuration
            test_data: Test data to send

        Returns:
            Result dictionary
        """
        try:
            url = self._get_credential_value(
                webhook_config.url_type,
                webhook_config.url_value
            )

            # Prepare payload
            payload = {
                "title": webhook_config.message_title,
                "body": webhook_config.message_body,
                "test": True,
                "data": test_data
            }

            # Add secret if configured
            headers = webhook_config.headers.copy()
            if webhook_config.secret_type and webhook_config.secret_value:
                secret = self._get_credential_value(
                    webhook_config.secret_type,
                    webhook_config.secret_value
                )
                headers["X-Webhook-Secret"] = secret

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.request(
                    webhook_config.method,
                    url,
                    headers=headers,
                    json=payload
                )
                response.raise_for_status()

            return {
                "success": True,
                "response": {
                    "status_code": response.status_code,
                    "body": response.text[:500]  # First 500 chars
                }
            }
        except Exception as e:
            return {"success": False, "error": str(e)}


# Export crud instance
crud_trigger = CRUDTrigger(Trigger)
