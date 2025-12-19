"""Add AI analysis and storage tables

Revision ID: 001_ai_analysis
Revises: 
Create Date: 2024-12-19

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '001_ai_analysis'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # AI Task Status Enum
    aitaskstatus_enum = postgresql.ENUM(
        'pending', 'processing', 'completed', 'failed',
        name='aitaskstatus',
        create_type=False
    )
    aitaskstatus_enum.create(op.get_bind(), checkfirst=True)
    
    # Defect Type Enum
    defecttype_enum = postgresql.ENUM(
        'crack', 'hotspot', 'snail_trail', 'cell_damage', 'delamination',
        'discoloration', 'broken_cell', 'pid', 'soiling', 'shading', 'unknown',
        name='defecttype',
        create_type=False
    )
    defecttype_enum.create(op.get_bind(), checkfirst=True)

    # AI Analysis Tasks Table
    op.create_table(
        'ai_analysis_tasks',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('organization_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('organizations.id'), nullable=False, index=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True, index=True),
        sa.Column('asset_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('smart_assets.id'), nullable=True, index=True),
        
        # Task status
        sa.Column('status', sa.Enum('pending', 'processing', 'completed', 'failed', name='aitaskstatus'), 
                  nullable=False, default='pending', index=True),
        sa.Column('progress', sa.Integer(), default=0),
        sa.Column('error_message', sa.Text(), nullable=True),
        
        # Image info
        sa.Column('original_image_key', sa.String(512), nullable=False),
        sa.Column('original_filename', sa.String(255), nullable=True),
        sa.Column('image_width', sa.Integer(), nullable=True),
        sa.Column('image_height', sa.Integer(), nullable=True),
        
        # Model info
        sa.Column('model_version', sa.String(50), nullable=True),
        sa.Column('sahi_enabled', sa.Boolean(), default=False),
        sa.Column('confidence_threshold', sa.Float(), default=0.40),
        
        # Timing
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('processing_time_ms', sa.Integer(), nullable=True),
        
        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), index=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # AI Detections Table
    op.create_table(
        'ai_detections',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('task_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('ai_analysis_tasks.id', ondelete='CASCADE'), nullable=False, index=True),
        
        # Defect info
        sa.Column('defect_type', sa.Enum('crack', 'hotspot', 'snail_trail', 'cell_damage', 'delamination',
                                         'discoloration', 'broken_cell', 'pid', 'soiling', 'shading', 'unknown',
                                         name='defecttype'), nullable=False, index=True),
        sa.Column('confidence', sa.Float(), nullable=False),
        
        # Bounding box (YOLO)
        sa.Column('bbox_x', sa.Float(), nullable=False),
        sa.Column('bbox_y', sa.Float(), nullable=False),
        sa.Column('bbox_width', sa.Float(), nullable=False),
        sa.Column('bbox_height', sa.Float(), nullable=False),
        
        # Segmentation (SAM2)
        sa.Column('segmentation_points', postgresql.JSONB(), nullable=True),
        
        # Additional metadata
        sa.Column('area_pixels', sa.Integer(), nullable=True),
        sa.Column('severity_score', sa.Float(), nullable=True),
        
        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), index=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # Indexes for performance
    op.create_index('ix_ai_tasks_org_status', 'ai_analysis_tasks', ['organization_id', 'status'])
    op.create_index('ix_ai_tasks_created', 'ai_analysis_tasks', ['created_at'])
    op.create_index('ix_ai_detections_defect', 'ai_detections', ['defect_type', 'confidence'])


def downgrade():
    # Drop indexes
    op.drop_index('ix_ai_detections_defect', table_name='ai_detections')
    op.drop_index('ix_ai_tasks_created', table_name='ai_analysis_tasks')
    op.drop_index('ix_ai_tasks_org_status', table_name='ai_analysis_tasks')
    
    # Drop tables
    op.drop_table('ai_detections')
    op.drop_table('ai_analysis_tasks')
    
    # Drop enums
    sa.Enum(name='defecttype').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='aitaskstatus').drop(op.get_bind(), checkfirst=True)
