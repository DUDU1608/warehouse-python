"""Add Buyer module tables"""

from alembic import op
import sqlalchemy as sa

# ---- Identifiers ----
revision = "c4e48601fefe"
down_revision = "b6f7436eccf6"   # baseline in your repo
branch_labels = None
depends_on = None


def upgrade():
    # --- buyer ---
    op.create_table(
        "buyer",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("buyer_name", sa.String(length=150), nullable=False),
        sa.Column("mobile_no", sa.String(length=20), nullable=False),
        sa.Column("address", sa.String(length=255)),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_buyer_buyer_name", "buyer", ["buyer_name"])
    op.create_index("ix_buyer_mobile_no", "buyer", ["mobile_no"], unique=True)

    # --- buyer_sale ---
    op.create_table(
        "buyer_sale",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("rst_no", sa.String(length=50), nullable=False),
        sa.Column("warehouse", sa.String(length=150)),
        sa.Column("buyer_id", sa.Integer(), nullable=False),
        sa.Column("buyer_name", sa.String(length=150)),
        sa.Column("mobile", sa.String(length=20)),
        sa.Column("commodity", sa.String(length=50), nullable=False),
        sa.Column("quantity", sa.Float(), nullable=False),
        sa.Column("rate", sa.Float(), nullable=False),
        sa.Column("cost", sa.Float(), nullable=False),
        sa.Column("handling_charge", sa.Float(), server_default=sa.text("0")),
        sa.Column("net_cost", sa.Float(), nullable=False),
        sa.Column("quality", sa.String(length=20)),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["buyer_id"], ["buyer.id"]),
    )
    op.create_index("ix_buyer_sale_date", "buyer_sale", ["date"])

    # --- buyer_payment ---
    op.create_table(
        "buyer_payment",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("buyer_id", sa.Integer(), nullable=False),
        sa.Column("buyer_name", sa.String(length=150)),
        sa.Column("mobile_no", sa.String(length=20)),
        sa.Column("commodity", sa.String(length=50)),
        sa.Column("warehouse", sa.String(length=150)),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("reference", sa.String(length=100)),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["buyer_id"], ["buyer.id"]),
    )


def downgrade():
    op.drop_table("buyer_payment")
    op.drop_index("ix_buyer_sale_date", table_name="buyer_sale")
    op.drop_table("buyer_sale")
    op.drop_index("ix_buyer_mobile_no", table_name="buyer")
    op.drop_index("ix_buyer_buyer_name", table_name="buyer")
    op.drop_table("buyer")
