"""initial

Revision ID: 0001
Revises: 
Create Date: 2026-08-17 05:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '0001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create users table
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('hashed_password', sa.String(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.create_index(op.f('ix_users_id'), 'users', ['id'], unique=False)

    # 2. Create accounts table
    op.create_table(
        'accounts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=True),
        sa.Column('balance', sa.Float(), nullable=True),
        sa.Column('margin', sa.Float(), nullable=True),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_accounts_id'), 'accounts', ['id'], unique=False)

    # 3. Create trades table
    op.create_table(
        'trades',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('symbol', sa.String(), nullable=False),
        sa.Column('direction', sa.String(), nullable=False),
        sa.Column('price', sa.Float(), nullable=False),
        sa.Column('quantity', sa.Float(), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('execution_type', sa.String(), nullable=True),
        sa.Column('status', sa.String(), nullable=True),
        sa.Column('pnl', sa.Float(), nullable=True),
        sa.Column('account_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_trades_id'), 'trades', ['id'], unique=False)
    op.create_index(op.f('ix_trades_symbol'), 'trades', ['symbol'], unique=False)
    op.create_index(op.f('ix_trades_timestamp'), 'trades', ['timestamp'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_trades_timestamp'), table_name='trades')
    op.drop_index(op.f('ix_trades_symbol'), table_name='trades')
    op.drop_index(op.f('ix_trades_id'), table_name='trades')
    op.drop_table('trades')
    
    op.drop_index(op.f('ix_accounts_id'), table_name='accounts')
    op.drop_table('accounts')
    
    op.drop_index(op.f('ix_users_id'), table_name='users')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_table('users')
