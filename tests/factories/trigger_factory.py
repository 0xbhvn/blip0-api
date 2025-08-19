"""Factories for Trigger, EmailTrigger, and WebhookTrigger models."""

import uuid
from datetime import UTC, datetime
from typing import Any

import factory
from faker import Faker

from src.app.models.trigger import EmailTrigger, Trigger, WebhookTrigger

from .base import BaseFactory

fake = Faker()


class TriggerFactory(BaseFactory):
    """Factory for creating Trigger instances with realistic test data."""

    class Meta:
        model = Trigger

    # Core trigger fields
    id = factory.LazyFunction(uuid.uuid4)
    tenant_id = factory.Faker('uuid4')
    name = factory.Faker('catch_phrase')
    slug = factory.Sequence(lambda n: f"trigger-{n:04d}")
    trigger_type = factory.Iterator(["email", "webhook"])
    description = factory.Faker('text', max_nb_chars=200)

    # Status fields
    active = True
    validated = False
    validation_errors = None
    last_validated_at = None

    # Timestamps
    created_at = factory.LazyFunction(lambda: datetime.now(UTC))
    updated_at = factory.LazyFunction(lambda: datetime.now(UTC))

    @factory.post_generation
    def create_config(self, create: bool, extracted: Any, **kwargs: Any) -> None:
        """Create associated trigger config after trigger creation."""
        if not create:
            return

        if self.trigger_type == "email":
            EmailTriggerFactory.create(trigger_id=self.id, **kwargs.get('email_config', {}))
        elif self.trigger_type == "webhook":
            WebhookTriggerFactory.create(trigger_id=self.id, **kwargs.get('webhook_config', {}))

    @classmethod
    def create_email_trigger(cls, **kwargs: Any) -> Trigger:
        """
        Create an email trigger with configuration.

        Args:
            **kwargs: Additional trigger attributes

        Returns:
            Trigger instance with email configuration
        """
        defaults = {
            'trigger_type': 'email',
            'name': f"Email Alert - {fake.catch_phrase()}",
        }
        defaults.update(kwargs)
        return cls.create(**defaults)

    @classmethod
    def create_webhook_trigger(cls, **kwargs: Any) -> Trigger:
        """
        Create a webhook trigger with configuration.

        Args:
            **kwargs: Additional trigger attributes

        Returns:
            Trigger instance with webhook configuration
        """
        defaults = {
            'trigger_type': 'webhook',
            'name': f"Webhook Alert - {fake.catch_phrase()}",
        }
        defaults.update(kwargs)
        return cls.create(**defaults)

    @classmethod
    def create_validated_trigger(cls, **kwargs: Any) -> Trigger:
        """
        Create a validated trigger.

        Args:
            **kwargs: Additional trigger attributes

        Returns:
            Validated Trigger instance
        """
        defaults = {
            'validated': True,
            'last_validated_at': factory.LazyFunction(lambda: datetime.now(UTC)),
            'validation_errors': None
        }
        defaults.update(kwargs)
        return cls.create(**defaults)

    @classmethod
    def create_invalid_trigger(cls, **kwargs: Any) -> Trigger:
        """
        Create a trigger with validation errors.

        Args:
            **kwargs: Additional trigger attributes

        Returns:
            Invalid Trigger instance
        """
        defaults = {
            'validated': False,
            'validation_errors': {
                "configuration": ["Invalid SMTP settings"],
                "credentials": ["Authentication failed"],
                "general": ["Test delivery failed"]
            },
            'last_validated_at': factory.LazyFunction(lambda: datetime.now(UTC))
        }
        defaults.update(kwargs)
        return cls.create(**defaults)

    # Factory traits for different trigger states
    class Params:
        """Parameters for factory traits."""
        email = factory.Trait(trigger_type="email")
        webhook = factory.Trait(trigger_type="webhook")
        is_inactive = factory.Trait(active=False)

        is_validated = factory.Trait(
            validated=True,
            last_validated_at=factory.LazyFunction(lambda: datetime.now(UTC))
        )

        with_validation_errors = factory.Trait(
            validated=False,
            validation_errors=factory.LazyFunction(lambda: {
                "general": [fake.sentence()]
            })
        )


class EmailTriggerFactory(BaseFactory):
    """Factory for creating EmailTrigger instances."""

    class Meta:
        model = EmailTrigger

    # Foreign key to trigger
    trigger_id = factory.Faker('uuid4')

    # SMTP configuration
    host = factory.Iterator([
        "smtp.gmail.com",
        "smtp.outlook.com",
        "smtp.sendgrid.net",
        "smtp.mailgun.org",
        "smtp.postmarkapp.com"
    ])
    port = factory.Iterator([465, 587, 25])

    # Credentials (using Plain type for testing)
    username_type = "Plain"
    username_value = factory.Faker('email')
    password_type = "Plain"
    password_value = factory.Faker('password')

    # Email composition
    sender = factory.LazyAttribute(lambda obj: obj.username_value)
    recipients = factory.LazyFunction(lambda: [
        fake.email(),
        fake.email()
    ][:fake.random_int(min=1, max=3)])

    message_title = factory.LazyFunction(lambda:
        f"Alert: {fake.catch_phrase()} - {{{{ monitor_name }}}}"
    )
    message_body = factory.LazyFunction(lambda: f"""
Alert triggered for monitor: {{{{ monitor_name }}}}

Details:
- Network: {{{{ network }}}}
- Block: {{{{ block_number }}}}
- Transaction: {{{{ transaction_hash }}}}

{fake.text(max_nb_chars=200)}

Generated at {{{{ timestamp }}}}
    """.strip())

    # Timestamps
    created_at = factory.LazyFunction(lambda: datetime.now(UTC))
    updated_at = factory.LazyFunction(lambda: datetime.now(UTC))

    @classmethod
    def create_gmail_config(cls, **kwargs: Any) -> EmailTrigger:
        """
        Create Gmail SMTP configuration.

        Args:
            **kwargs: Additional email trigger attributes

        Returns:
            EmailTrigger instance with Gmail settings
        """
        defaults = {
            'host': 'smtp.gmail.com',
            'port': 587,
            'username_value': f"{fake.user_name()}@gmail.com",
        }
        defaults.update(kwargs)
        return cls.create(**defaults)

    @classmethod
    def create_sendgrid_config(cls, **kwargs: Any) -> EmailTrigger:
        """
        Create SendGrid SMTP configuration.

        Args:
            **kwargs: Additional email trigger attributes

        Returns:
            EmailTrigger instance with SendGrid settings
        """
        defaults = {
            'host': 'smtp.sendgrid.net',
            'port': 587,
            'username_value': 'apikey',
            'password_value': f"SG.{fake.lexify('?' * 22)}.{fake.lexify('?' * 43)}",
        }
        defaults.update(kwargs)
        return cls.create(**defaults)

    @classmethod
    def create_with_environment_creds(cls, **kwargs: Any) -> EmailTrigger:
        """
        Create email trigger with environment variable credentials.

        Args:
            **kwargs: Additional email trigger attributes

        Returns:
            EmailTrigger instance using environment variables
        """
        defaults = {
            'username_type': 'Environment',
            'username_value': 'EMAIL_SMTP_USERNAME',
            'password_type': 'Environment',
            'password_value': 'EMAIL_SMTP_PASSWORD',
        }
        defaults.update(kwargs)
        return cls.create(**defaults)

    @classmethod
    def create_with_vault_creds(cls, **kwargs: Any) -> EmailTrigger:
        """
        Create email trigger with HashiCorp Vault credentials.

        Args:
            **kwargs: Additional email trigger attributes

        Returns:
            EmailTrigger instance using HashiCorp Vault
        """
        defaults = {
            'username_type': 'HashicorpCloudVault',
            'username_value': 'secret/email/smtp:username',
            'password_type': 'HashicorpCloudVault',
            'password_value': 'secret/email/smtp:password',
        }
        defaults.update(kwargs)
        return cls.create(**defaults)

    # Factory traits for different email configurations
    class Params:
        """Parameters for factory traits."""
        gmail = factory.Trait(
            host="smtp.gmail.com",
            port=587,
            username_value=factory.LazyFunction(lambda: f"{fake.user_name()}@gmail.com")
        )

        outlook = factory.Trait(
            host="smtp.outlook.com",
            port=587,
            username_value=factory.LazyFunction(lambda: f"{fake.user_name()}@outlook.com")
        )

        sendgrid = factory.Trait(
            host="smtp.sendgrid.net",
            port=587,
            username_value="apikey"
        )

        environment_creds = factory.Trait(
            username_type="Environment",
            username_value="EMAIL_SMTP_USERNAME",
            password_type="Environment",
            password_value="EMAIL_SMTP_PASSWORD"
        )

        vault_creds = factory.Trait(
            username_type="HashicorpCloudVault",
            username_value="secret/email/smtp:username",
            password_type="HashicorpCloudVault",
            password_value="secret/email/smtp:password"
        )


class WebhookTriggerFactory(BaseFactory):
    """Factory for creating WebhookTrigger instances."""

    class Meta:
        model = WebhookTrigger

    # Foreign key to trigger
    trigger_id = factory.Faker('uuid4')

    # Webhook configuration
    url_type = "Plain"
    url_value = factory.Faker('url')
    method = "POST"

    # Headers
    headers = factory.LazyFunction(lambda: {
        "Content-Type": "application/json",
        "User-Agent": f"Blip0-Monitor/{fake.numerify('#.#.#')}",
        "X-Webhook-Source": "blip0-monitor"
    })

    # Message templates
    message_title = factory.LazyFunction(lambda:
        "Monitor Alert: {{ monitor_name }}"
    )
    message_body = factory.LazyFunction(lambda: """{
    "alert": {
        "monitor": "{{ monitor_name }}",
        "network": "{{ network }}",
        "block_number": {{ block_number }},
        "transaction_hash": "{{ transaction_hash }}",
        "timestamp": "{{ timestamp }}",
        "details": {{ match_data }}
    }
}""")

    # Optional secret
    secret_type = None
    secret_value = None

    # Timestamps
    created_at = factory.LazyFunction(lambda: datetime.now(UTC))
    updated_at = factory.LazyFunction(lambda: datetime.now(UTC))

    @classmethod
    def create_slack_webhook(cls, **kwargs: Any) -> WebhookTrigger:
        """
        Create Slack webhook configuration.

        Args:
            **kwargs: Additional webhook trigger attributes

        Returns:
            WebhookTrigger instance for Slack
        """
        defaults = {
            'url_value': f"https://hooks.slack.com/services/{fake.lexify('?' * 9)}/{fake.lexify('?' * 11)}/{fake.lexify('?' * 24)}",
            'headers': {
                "Content-Type": "application/json"
            },
            'message_body': """{
    "text": "Monitor Alert: {{ monitor_name }}",
    "blocks": [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "*Alert:* {{ monitor_name }}\\n*Network:* {{ network }}\\n*Block:* {{ block_number }}"
            }
        }
    ]
}"""
        }
        defaults.update(kwargs)
        return cls.create(**defaults)

    @classmethod
    def create_discord_webhook(cls, **kwargs: Any) -> WebhookTrigger:
        """
        Create Discord webhook configuration.

        Args:
            **kwargs: Additional webhook trigger attributes

        Returns:
            WebhookTrigger instance for Discord
        """
        defaults = {
            'url_value': f"https://discord.com/api/webhooks/{fake.numerify('##################')}/{fake.lexify('?' * 68)}",
            'headers': {
                "Content-Type": "application/json"
            },
            'message_body': """{
    "embeds": [
        {
            "title": "Monitor Alert",
            "description": "{{ monitor_name }}",
            "color": 15158332,
            "fields": [
                {
                    "name": "Network",
                    "value": "{{ network }}",
                    "inline": true
                },
                {
                    "name": "Block",
                    "value": "{{ block_number }}",
                    "inline": true
                }
            ],
            "timestamp": "{{ timestamp }}"
        }
    ]
}"""
        }
        defaults.update(kwargs)
        return cls.create(**defaults)

    @classmethod
    def create_with_environment_url(cls, **kwargs: Any) -> WebhookTrigger:
        """
        Create webhook trigger with environment variable URL.

        Args:
            **kwargs: Additional webhook trigger attributes

        Returns:
            WebhookTrigger instance using environment variable
        """
        defaults = {
            'url_type': 'Environment',
            'url_value': 'WEBHOOK_URL',
        }
        defaults.update(kwargs)
        return cls.create(**defaults)

    @classmethod
    def create_with_vault_url(cls, **kwargs: Any) -> WebhookTrigger:
        """
        Create webhook trigger with HashiCorp Vault URL.

        Args:
            **kwargs: Additional webhook trigger attributes

        Returns:
            WebhookTrigger instance using HashiCorp Vault
        """
        defaults = {
            'url_type': 'HashicorpCloudVault',
            'url_value': 'secret/webhooks/alerts:url',
        }
        defaults.update(kwargs)
        return cls.create(**defaults)

    @classmethod
    def create_with_secret(cls, **kwargs: Any) -> WebhookTrigger:
        """
        Create webhook trigger with secret for authentication.

        Args:
            **kwargs: Additional webhook trigger attributes

        Returns:
            WebhookTrigger instance with secret
        """
        defaults = {
            'secret_type': 'Plain',
            'secret_value': fake.sha256(),
            'headers': {
                "Content-Type": "application/json",
                "X-Hub-Signature": "sha256={{ secret }}",
                "User-Agent": "Blip0-Monitor"
            }
        }
        defaults.update(kwargs)
        return cls.create(**defaults)

    # Factory traits for different webhook configurations
    class Params:
        """Parameters for factory traits."""
        slack = factory.Trait(
            url_value=factory.LazyFunction(
                lambda: f"https://hooks.slack.com/services/{fake.lexify('?' * 9)}/{fake.lexify('?' * 11)}/{fake.lexify('?' * 24)}"
            ),
            message_body=factory.LazyFunction(lambda: """{
    "text": "Monitor Alert: {{ monitor_name }}",
    "attachments": [
        {
            "color": "warning",
            "fields": [
                {
                    "title": "Network",
                    "value": "{{ network }}",
                    "short": true
                },
                {
                    "title": "Block",
                    "value": "{{ block_number }}",
                    "short": true
                }
            ]
        }
    ]
}""")
        )

        discord = factory.Trait(
            url_value=factory.LazyFunction(
                lambda: f"https://discord.com/api/webhooks/{fake.numerify('##################')}/{fake.lexify('?' * 68)}"
            )
        )

        generic = factory.Trait(
            url_value=factory.Faker('url'),
            headers=factory.LazyFunction(lambda: {
                "Content-Type": "application/json",
                "User-Agent": "Blip0-Monitor"
            })
        )

        environment_url = factory.Trait(
            url_type="Environment",
            url_value="WEBHOOK_URL"
        )

        vault_url = factory.Trait(
            url_type="HashicorpCloudVault",
            url_value="secret/webhooks/alerts:url"
        )

        with_secret = factory.Trait(
            secret_type="Plain",
            secret_value=factory.Faker('sha256')
        )

        get_method = factory.Trait(method="GET")
        put_method = factory.Trait(method="PUT")
        patch_method = factory.Trait(method="PATCH")
