"""ko-sroberta 임베딩 생성기.

TP_TRAVEL_AI의 app/core/embedding.py와 같은 모델·차원을 쓴다.
모델이 다르면 같은 테이블에 서로 비교 불가능한 벡터가 섞이므로,
차원이 설정과 다르면 즉시 실패시킨다.

torch/sentence-transformers는 무겁기 때문에 여기서만 지연 import 한다.
(수집 잡만 돌릴 때는 설치되어 있지 않아도 된다.)
"""
import logging
from typing import List, Optional

log = logging.getLogger(__name__)


class EmbeddingService:
    def __init__(self, model_name: str, dimension: int, device: str = "cpu"):
        self.model_name = model_name
        self.dimension = dimension
        self.device = device
        self._model = None  # type: Optional[object]

    def _ensure_model(self):
        if self._model is not None:
            return self._model
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError(
                "sentence-transformers가 설치되어 있지 않습니다. "
                "동기화 잡을 실행하려면 'pip install -r requirements-embed.txt'를 먼저 실행하세요."
            ) from exc

        log.info("임베딩 모델 로딩: %s (device=%s)", self.model_name, self.device)
        model = SentenceTransformer(self.model_name, device=self.device)
        actual = model.get_sentence_embedding_dimension()
        if actual != self.dimension:
            raise RuntimeError(
                "임베딩 차원 불일치: 모델 {0}차원 vs 설정 {1}차원. "
                "EMBEDDING_DIMENSION과 travel_spots.embedding 컬럼을 맞춰주세요.".format(
                    actual, self.dimension
                )
            )
        self._model = model
        return model

    def embed_texts(self, texts: List[str], batch_size: int = 64) -> List[List[float]]:
        model = self._ensure_model()
        vectors = model.encode(
            texts,
            batch_size=batch_size,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return [v.tolist() for v in vectors]


def to_pgvector_literal(vector: List[float]) -> str:
    """pgvector가 받는 '[0.1,0.2,...]' 문자열 리터럴로 변환."""
    return "[" + ",".join("{0:.7f}".format(v) for v in vector) + "]"
