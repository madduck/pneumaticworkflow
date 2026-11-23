import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('authentication', '0006_auto_20251118_1144'),
        ('accounts', '0147_merge_python312_django52'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='OIDCLoginAttempt',
            fields=[
                ('state', models.CharField(max_length=43, primary_key=True,
                                           serialize=False)),
                ('browser_binding', models.CharField(max_length=64)),
                ('nonce', models.CharField(max_length=43)),
                ('verifier', models.CharField(max_length=43)),
                ('expires_at', models.DateTimeField(db_index=True)),
            ],
        ),
        migrations.CreateModel(
            name='OIDCIdentity',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True,
                                        serialize=False, verbose_name='ID')),
                ('issuer', models.CharField(max_length=512)),
                ('subject', models.CharField(max_length=255)),
                ('admin_granted', models.BooleanField(default=False)),
                ('managed_groups', models.ManyToManyField(
                    blank=True, to='accounts.usergroup',
                )),
                ('user', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='oidc_identity', to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={'constraints': [models.UniqueConstraint(
                fields=('issuer', 'subject'),
                name='oidc_identity_issuer_subject_unique',
            )]},
        ),
    ]
