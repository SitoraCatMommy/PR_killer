from app.repositories.aggregation_snapshot_repository import AggregationSnapshotRepository
from app.repositories.dashboard_repository import DashboardRepository
from app.repositories.entity_repository import EntityRepository
from app.repositories.insight_repository import InsightRepository
from app.repositories.material_repository import MaterialRepository
from app.repositories.project_repository import ProjectRepository
from app.repositories.research_entity_repository import ExtractedEntityRepository
from app.repositories.research_summary_repository import ResearchSummaryRepository
from app.repositories.source_audio_repository import SourceAudioRepository
from app.repositories.source_document_repository import SourceDocumentRepository
from app.repositories.text_chunk_repository import TextChunkRepository
from app.repositories.transcript_repository import TranscriptRepository

__all__ = [
    "AggregationSnapshotRepository",
    "MaterialRepository",
    "InsightRepository",
    "EntityRepository",
    "DashboardRepository",
    "ProjectRepository",
    "SourceDocumentRepository",
    "SourceAudioRepository",
    "TranscriptRepository",
    "TextChunkRepository",
    "ExtractedEntityRepository",
    "ResearchSummaryRepository",
]
