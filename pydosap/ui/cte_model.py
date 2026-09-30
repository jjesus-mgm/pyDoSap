"""Modelo da tabela de CT-es (equivale à tabela tbCTEs da planilha MENU)."""
from __future__ import annotations

from typing import Any, Iterable

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QColor

from ..cte_columns import (
    ALINHAMENTO_ESQUERDA, COL_LANCADO, COL_LANCAR, COL_PEDIDO, COL_RESPOSTA, COLUNAS_DATA,
    COLUNAS_MOEDA, LARGURAS, LINKS, ordenar_colunas, rotulo,
)
from ..formatting import data_br, moeda_brl

CHECKS = {COL_LANCAR, COL_LANCADO}
EDITAVEIS = {"codFornecedor", "categoria", COL_PEDIDO}

CORES = {
    "ok": QColor("#E6F4EA"),
    "erro": QColor("#FCE8E6"),
    "processando": QColor("#FFF4CE"),
}
COR_LINK = QColor("#0B5FFF")
# cor do texto quando a formatação baseada em status estiver ativa (fundo claro
# nas três situações acima, mesmo com o app no tema escuro — por isso o texto
# preto; sem isso, o texto claro do tema ficava ilegível sobre o fundo claro)
COR_TEXTO_PADRAO = QColor("#000000")


def _marcado(valor: Any) -> bool:
    if isinstance(valor, Qt.CheckState):
        return valor == Qt.CheckState.Checked
    try:
        return int(valor) == Qt.CheckState.Checked.value
    except (TypeError, ValueError):
        return bool(valor)


def _formatar(coluna: str, valor: Any) -> str:
    if valor is None:
        return ""
    if coluna in COLUNAS_DATA:
        return data_br(valor)
    if coluna in COLUNAS_MOEDA:
        return moeda_brl(valor)
    if isinstance(valor, bool):
        return "Sim" if valor else "Não"
    if isinstance(valor, float):
        return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return str(valor).replace("\r", "").replace("\n", " ⏎ ")


class CteTableModel(QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows: list[dict] = []
        self._status: list[str] = []
        self._cols: list[str] = []
        self._travado = False

    # ------------------------------------------------------------- carga
    def load(self, rows: list[dict]) -> None:
        self.beginResetModel()
        self._rows = [dict(r) for r in rows]
        self._status = [""] * len(self._rows)
        self._cols = self._descobrir_colunas(self._rows)
        for r in self._rows:
            r[COL_LANCAR] = bool(r.get(COL_LANCAR))
        self.endResetModel()

    @staticmethod
    def _descobrir_colunas(rows: list[dict]) -> list[str]:
        vistas: dict[str, None] = {}
        for r in rows:
            for k in r:
                vistas.setdefault(k, None)
        # pedido/resposta/lancar são colunas da UI, preenchidas depois da busca —
        # precisam existir mesmo que a API não as devolva na primeira carga.
        for col in (COL_LANCAR, COL_PEDIDO, COL_RESPOSTA):
            vistas.setdefault(col, None)
        return ordenar_colunas(vistas.keys())

    # --------------------------------------------------- API do QAbstractTableModel
    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._cols)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return rotulo(self._cols[section])
        return None

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        linha = self._rows[index.row()]
        col = self._cols[index.column()]
        valor = linha.get(col)

        if role == Qt.ItemDataRole.CheckStateRole and col in CHECKS:
            return Qt.CheckState.Checked if valor else Qt.CheckState.Unchecked
        if role == Qt.ItemDataRole.DisplayRole:
            if col in CHECKS:
                return None
            if col in LINKS:
                return LINKS[col] if valor else ""
            return _formatar(col, valor)
        if role == Qt.ItemDataRole.EditRole and col in EDITAVEIS:
            return "" if valor is None else str(valor)
        if role == Qt.ItemDataRole.UserRole:  # chave de ordenação
            if isinstance(valor, bool):
                return int(valor)
            if valor is None:
                return ""
            return valor if isinstance(valor, (int, float, str)) else str(valor)
        if role == Qt.ItemDataRole.BackgroundRole:
            return CORES.get(self._status[index.row()])
        if role == Qt.ItemDataRole.ForegroundRole:
            status = self._status[index.row()]
            if col in LINKS and valor:
                return COR_LINK
            if status in CORES:
                return COR_TEXTO_PADRAO
        if role == Qt.ItemDataRole.ToolTipRole and col in (COL_RESPOSTA, "observacao") and valor:
            return str(valor)
        if role == Qt.ItemDataRole.TextAlignmentRole:
            if col in CHECKS or col not in ALINHAMENTO_ESQUERDA:
                if col in ALINHAMENTO_ESQUERDA:
                    return Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
                return Qt.AlignmentFlag.AlignCenter
            return Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        return None

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        if not self._travado:
            col = self._cols[index.column()]
            if col == COL_LANCAR:
                flags |= Qt.ItemFlag.ItemIsUserCheckable
            elif col in EDITAVEIS:
                flags |= Qt.ItemFlag.ItemIsEditable
        return flags

    def setData(self, index: QModelIndex, value: Any, role: int = Qt.ItemDataRole.EditRole) -> bool:
        if not index.isValid() or self._travado:
            return False
        col = self._cols[index.column()]
        if col == COL_LANCAR and role == Qt.ItemDataRole.CheckStateRole:
            self._rows[index.row()][col] = _marcado(value)
        elif col in EDITAVEIS and role == Qt.ItemDataRole.EditRole:
            self._rows[index.row()][col] = str(value).strip()
        else:
            return False
        self.dataChanged.emit(index, index, [])
        return True

    # ----------------------------------------------------------- consultas
    def colunas(self) -> list[str]:
        return list(self._cols)

    def largura_coluna(self, coluna: str) -> int | None:
        return LARGURAS.get(coluna)

    def linha(self, indice: int) -> dict:
        """Cópia dos dados (já formatados como na tela) da linha, na ordem das
        colunas — usada pela exportação para Excel."""
        original = self._rows[indice]
        return {
            col: (LINKS[col] if col in LINKS and original.get(col) else original.get(col))
            for col in self._cols
        }

    def total_marcados(self) -> int:
        return sum(1 for r in self._rows if r.get(COL_LANCAR))

    def linhas_marcadas(self) -> list[tuple[int, dict]]:
        """(índice da linha, cópia dos dados) dos CT-es marcados em 'Lançar'."""
        return [(i, dict(r)) for i, r in enumerate(self._rows) if r.get(COL_LANCAR)]

    def url(self, index: QModelIndex) -> str | None:
        col = self._cols[index.column()]
        if col in LINKS:
            valor = str(self._rows[index.row()].get(col) or "").strip()
            if valor.lower().startswith(("http://", "https://")):
                return valor
        return None

    # ------------------------------------------------------------ alterações
    def travar(self, travado: bool) -> None:
        """Impede edição enquanto o lançamento está em andamento."""
        self._travado = travado

    def marcar(self, indices: Iterable[int], marcado: bool) -> None:
        if self._travado or not self._rows:
            return
        for i in indices:
            self._rows[i][COL_LANCAR] = marcado
        col = self._cols.index(COL_LANCAR)
        self.dataChanged.emit(self.index(0, col), self.index(len(self._rows) - 1, col), [])

    def set_status(self, linha: int, status: str) -> None:
        self._status[linha] = status
        self.dataChanged.emit(
            self.index(linha, 0), self.index(linha, len(self._cols) - 1),
            [Qt.ItemDataRole.BackgroundRole],
        )

    def set_resultado(self, linha: int, pedido: str, resposta: str, sucesso: bool) -> None:
        r = self._rows[linha]
        if pedido:
            r[COL_PEDIDO] = pedido
        r[COL_RESPOSTA] = resposta
        if sucesso:
            if COL_LANCADO in self._cols:
                r[COL_LANCADO] = True
            r[COL_LANCAR] = False  # evita lançar duas vezes o mesmo CT-e
        self.dataChanged.emit(
            self.index(linha, 0), self.index(linha, len(self._cols) - 1), []
        )
