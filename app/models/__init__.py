from app.models.base import Base

# Import order matters for SQLAlchemy mapper configuration (forward refs / relationships).
from app.models.project import Project
from app.models.source_document import SourceDocument
from app.models.interview_unit import InterviewUnit
from app.models.source_audio import SourceAudio
from app.models.audio_segment import AudioSegment
from app.models.transcript import Transcript
from app.models.transcript_segment import TranscriptSegment
from app.models.text_chunk import TextChunk
from app.models.entity_relationship import EntityRelationship
from app.models.extracted_entity import ExtractedEntity
from app.models.aggregation_snapshot import AggregationSnapshot
from app.models.research_summary import ResearchSummary
from app.models.research_batch import ResearchBatch
from app.models.research_batch_source import ResearchBatchSource
from app.models.research_batch_llm_cache import ResearchBatchLlmCache
from app.models.batch_public_report import BatchPublicReport
from app.models.project_llm_cache import ProjectLlmCache
from app.models.project_public_report import ProjectPublicReport
from app.models.project_public_report_token_redirect import ProjectPublicReportTokenRedirect
from app.models.research_report import ResearchReport

# Legacy material / insight pipeline
from app.models.dashboard_aggregate import DashboardAggregate
from app.models.insight import Insight
from app.models.insight_source_link import InsightSourceLink
from app.models.material import Material
from app.models.material_extracted_entity import MaterialExtractedEntity

__all__ = [
    "AggregationSnapshot",
    "AudioSegment",
    "Base",
    "BatchPublicReport",
    "DashboardAggregate",
    "EntityRelationship",
    "ExtractedEntity",
    "Insight",
    "InsightSourceLink",
    "InterviewUnit",
    "Material",
    "MaterialExtractedEntity",
    "Project",
    "ProjectLlmCache",
    "ProjectPublicReport",
    "ProjectPublicReportTokenRedirect",
    "ResearchBatch",
    "ResearchBatchLlmCache",
    "ResearchBatchSource",
    "ResearchReport",
    "ResearchSummary",
    "SourceAudio",
    "SourceDocument",
    "TextChunk",
    "Transcript",
    "TranscriptSegment",
]
