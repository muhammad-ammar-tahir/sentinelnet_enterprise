"""initial_schema

Revision ID: 0001_initial
Revises: 
Create Date: 2026-11-23 16:50:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0001_initial'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. devices
    op.create_table(
        'devices',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('name', sa.String(length=128), nullable=False),
        sa.Column('device_type', sa.String(length=32), nullable=False),
        sa.Column('ip_address', sa.String(length=45), nullable=True),
        sa.Column('mac_address', sa.String(length=17), nullable=True),
        sa.Column('dpid', sa.String(length=32), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='active'),
        sa.Column('location', sa.String(length=100), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_devices_id'), 'devices', ['id'], unique=False)
    op.create_index(op.f('ix_devices_dpid'), 'devices', ['dpid'], unique=False)

    # 2. links
    op.create_table(
        'links',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('src_device_id', sa.String(length=64), nullable=False),
        sa.Column('dst_device_id', sa.String(length=64), nullable=False),
        sa.Column('src_port', sa.Integer(), nullable=False),
        sa.Column('dst_port', sa.Integer(), nullable=False),
        sa.Column('link_type', sa.String(length=20), nullable=False, server_default='primary'),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='up'),
        sa.Column('bandwidth_mbps', sa.Float(), nullable=False, server_default='100.0'),
        sa.Column('current_utilization', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('latency_ms', sa.Float(), nullable=False, server_default='1.0'),
        sa.Column('packet_loss_rate', sa.Float(), nullable=False, server_default='0.0'),
        sa.ForeignKeyConstraint(['dst_device_id'], ['devices.id'], ),
        sa.ForeignKeyConstraint(['src_device_id'], ['devices.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_links_id'), 'links', ['id'], unique=False)

    # 3. incidents
    op.create_table(
        'incidents',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('severity', sa.String(length=20), nullable=False),
        sa.Column('status', sa.String(length=30), nullable=False, server_default='detected'),
        sa.Column('affected_device_id', sa.String(length=64), nullable=True),
        sa.Column('affected_link_id', sa.String(length=64), nullable=True),
        sa.Column('root_cause', sa.Text(), nullable=True),
        sa.Column('confidence_score', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('detected_at', sa.DateTime(), nullable=False),
        sa.Column('resolved_at', sa.DateTime(), nullable=True),
        sa.Column('metadata_payload', sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(['affected_device_id'], ['devices.id'], ),
        sa.ForeignKeyConstraint(['affected_link_id'], ['links.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_incidents_id'), 'incidents', ['id'], unique=False)
    op.create_index('ix_incidents_status', 'incidents', ['status'], unique=False)
    op.create_index('ix_incidents_severity', 'incidents', ['severity'], unique=False)
    op.create_index('ix_incidents_detected_at_desc', 'incidents', [sa.text('detected_at DESC')], unique=False)

    # 4. recovery_actions
    op.create_table(
        'recovery_actions',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('incident_id', sa.String(length=64), nullable=False),
        sa.Column('action_type', sa.String(length=64), nullable=False),
        sa.Column('status', sa.String(length=30), nullable=False, server_default='pending'),
        sa.Column('target_dpid', sa.String(length=32), nullable=True),
        sa.Column('parameters', sa.JSON(), nullable=True),
        sa.Column('execution_duration_ms', sa.Float(), nullable=True),
        sa.Column('rollback_status', sa.String(length=30), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('executed_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['incident_id'], ['incidents.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_recovery_actions_id'), 'recovery_actions', ['id'], unique=False)
    op.create_index('ix_recovery_actions_incident_id', 'recovery_actions', ['incident_id'], unique=False)
    op.create_index('ix_recovery_actions_executed_at', 'recovery_actions', ['executed_at'], unique=False)

    # 5. metrics
    op.create_table(
        'metrics',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('device_id', sa.String(length=64), nullable=True),
        sa.Column('metric_name', sa.String(length=64), nullable=False),
        sa.Column('metric_value', sa.Float(), nullable=False),
        sa.Column('timestamp', sa.DateTime(), nullable=False),
        sa.Column('labels', sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(['device_id'], ['devices.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_metrics_metric_name'), 'metrics', ['metric_name'], unique=False)
    op.create_index(op.f('ix_metrics_timestamp'), 'metrics', ['timestamp'], unique=False)
    op.create_index('ix_metrics_device_id_timestamp_desc', 'metrics', ['device_id', sa.text('timestamp DESC')], unique=False)
    op.create_index('ix_metrics_timestamp_idx', 'metrics', ['timestamp'], unique=False)

    # 6. policies
    op.create_table(
        'policies',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('name', sa.String(length=128), nullable=False),
        sa.Column('rule_condition', sa.String(length=255), nullable=False),
        sa.Column('action_template', sa.String(length=64), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('priority', sa.Integer(), nullable=False, server_default='100'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_policies_id'), 'policies', ['id'], unique=False)

    # 7. users
    op.create_table(
        'users',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('username', sa.String(length=64), nullable=False),
        sa.Column('email', sa.String(length=128), nullable=False),
        sa.Column('hashed_password', sa.String(length=255), nullable=False),
        sa.Column('role', sa.String(length=32), nullable=False, server_default='operator'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_id'), 'users', ['id'], unique=False)
    op.create_index(op.f('ix_users_username'), 'users', ['username'], unique=True)
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)

    # 8. audit_logs
    op.create_table(
        'audit_logs',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('action', sa.String(length=64), nullable=False),
        sa.Column('actor', sa.String(length=64), nullable=False, server_default='system'),
        sa.Column('details', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_audit_logs_id'), 'audit_logs', ['id'], unique=False)
    op.create_index(op.f('ix_audit_logs_created_at'), 'audit_logs', ['created_at'], unique=False)


def downgrade() -> None:
    op.drop_table('audit_logs')
    op.drop_table('users')
    op.drop_table('policies')
    op.drop_table('metrics')
    op.drop_table('recovery_actions')
    op.drop_table('incidents')
    op.drop_table('links')
    op.drop_table('devices')
