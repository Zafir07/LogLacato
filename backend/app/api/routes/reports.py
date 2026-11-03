"""Relatórios para exportar: Excel (planilhas) e PDF (relatório da viagem)."""
import io
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db, require
from app.api.routes.analytics import Filters, filters, trip_comparison, volume_by_day
from app.api.routes.trips import trip_summary
from app.models import Alert, QualitySample, Telemetry, Trip, User

router = APIRouter(prefix="/api/v1/reports", tags=["Relatórios"])
BR = ZoneInfo("America/Sao_Paulo")
HEADER_FILL = PatternFill("solid", fgColor="0E2A22")


def _local(dt: datetime | None) -> datetime | None:
    return dt.astimezone(BR).replace(tzinfo=None) if dt else None


def _xlsx(name: str, sheets: list[tuple[str, list[str], list[list]]], note: str) -> StreamingResponse:
    wb = Workbook()
    wb.remove(wb.active)
    for title, header, rows in sheets:
        ws = wb.create_sheet(title[:31])
        ws.append(header)
        for c in ws[1]:
            c.font, c.fill = Font(bold=True, color="FFFFFF"), HEADER_FILL
        for r in rows:
            ws.append(r)
        for i, h in enumerate(header, start=1):
            width = max([len(str(h))] + [len(str(r[i - 1])) for r in rows[:200] if r[i - 1] is not None])
            ws.column_dimensions[get_column_letter(i)].width = min(max(10, width + 2), 50)
        ws.freeze_panes = "A2"
    info = wb.create_sheet("Sobre")
    info.append(["Gerado em", datetime.now(BR).strftime("%d/%m/%Y %H:%M")])
    info.append(["Observação", note])
    info.append(["Horários", "Fuso de Brasília (UTC−3)"])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(
        buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{name}"'})


def _note(f: Filters) -> str:
    sim = "inclui dados SIMULADOS" if f.include_simulated else "somente dados reais (simulados excluídos)"
    return f"Período {f.date_from.astimezone(BR):%d/%m/%Y %H:%M} a {f.date_to.astimezone(BR):%d/%m/%Y %H:%M}; {sim}."


@router.get("/trips.xlsx", summary="Relatório de viagens (Excel)")
def trips_xlsx(f: Filters = Depends(filters), db: Session = Depends(get_db), user: User = Depends(require("leitura"))):
    # Chamada direta (sem o limite de 50 da tela): o relatório traz todas as viagens do período.
    rows = trip_comparison(limit=5000, f=f, db=db, _=user)
    data = [[r["code"], r["status"], r["vehicle_plate"], r["driver_name"], _local(r["departure_at"]),
             r["volume_liters"], r["readings"], r["ph_avg"], r["milk_temp_max"], r["acidity_avg"],
             r["samples_rejected"], r["alerts"], "sim" if r["is_simulated"] else "não",
             f'{r["last_gps"]["lat"]:.5f}, {r["last_gps"]["lon"]:.5f}' if r["last_gps"] else None] for r in rows]
    header = ["Viagem", "Status", "Placa", "Motorista", "Saída", "Volume (L)", "Leituras válidas",
              "pH médio", "Temp. máx. leite (°C)", "Acidez média (°D)", "Coletas recusadas", "Alertas",
              "Simulada", "Última posição GPS"]
    days = volume_by_day(f=f, db=db, _=user)
    vol = [[d["day"], d["volume_liters"], d["trips"]] for d in days]
    return _xlsx("viagens.xlsx", [("Viagens", header, data),
                                  ("Volume por dia", ["Dia", "Volume (L)", "Viagens"], vol)], _note(f))


@router.get("/alerts.xlsx", summary="Histórico de alertas (Excel)")
def alerts_xlsx(f: Filters = Depends(filters), db: Session = Depends(get_db), _: User = Depends(require("leitura"))):
    stmt = select(Alert, Trip.code).outerjoin(Trip, Trip.id == Alert.trip_id).where(
        Alert.first_seen_at.between(f.date_from, f.date_to))
    if not f.include_simulated:
        stmt = stmt.where(Alert.is_simulated.is_(False))
    rows = db.execute(stmt.order_by(Alert.first_seen_at.desc())).all()
    data = [[a.id, a.severity, a.status, a.type, a.title, code, a.device_id,
             float(a.measured_value) if a.measured_value is not None else None,
             float(a.reference_min) if a.reference_min is not None else None,
             float(a.reference_max) if a.reference_max is not None else None,
             a.occurrences, _local(a.first_seen_at), _local(a.last_seen_at), _local(a.acknowledged_at),
             _local(a.closed_at), a.close_reason, a.description] for a, code in rows]
    header = ["Id", "Severidade", "Status", "Tipo", "Título", "Viagem", "Dispositivo", "Valor medido", "Ref. mín",
              "Ref. máx", "Ocorrências", "Início", "Última", "Reconhecido", "Encerrado", "Motivo", "Descrição"]
    return _xlsx("alertas.xlsx", [("Alertas", header, data)], _note(f))


@router.get("/telemetry.xlsx", summary="Leituras de temperatura e pH de uma viagem (Excel)")
def telemetry_xlsx(trip_id: int, db: Session = Depends(get_db), _: User = Depends(require("leitura"))):
    t = db.get(Trip, trip_id)
    if not t:
        raise HTTPException(404, "viagem não encontrada")
    rows = db.scalars(select(Telemetry).where(Telemetry.trip_id == trip_id).order_by(Telemetry.measured_at)).all()
    n = lambda v: float(v) if v is not None else None  # noqa: E731
    data = [[_local(r.measured_at), _local(r.received_at), r.time_source, n(r.ph), n(r.ph_voltage),
             n(r.milk_temperature), n(r.air_temperature), n(r.air_humidity), n(r.lat), n(r.lon),
             "fila" if r.buffered else "ao vivo", r.validation_status, r.sensor_flags, r.msg_id] for r in rows]
    header = ["Medida em", "Recebida em", "Fonte do horário", "pH", "Tensão Po (V)", "Temp. leite (°C)",
              "Temp. ar (°C)", "Umidade ar (%)", "Latitude", "Longitude", "Origem", "Validação", "Flags", "msg_id"]
    samples = db.scalars(select(QualitySample).where(QualitySample.trip_id == trip_id)
                         .order_by(QualitySample.collected_at)).all()
    sdata = [[_local(s.collected_at), s.producer, n(s.acidity_dornic), n(s.density), s.volume_liters,
              n(s.milk_temperature), n(s.ph_manual), s.seal_code, s.decision, s.notes] for s in samples]
    sheader = ["Coletada em", "Produtor", "Acidez (°D)", "Densidade (g/mL)", "Volume (L)", "Temp. (°C)",
               "pH manual", "Amostra testemunha", "Decisão", "Observações"]
    note = f"Viagem {t.code}" + (" — dados SIMULADOS" if t.is_simulated else "")
    return _xlsx(f"leituras-{t.code}.xlsx", [("Leituras", header, data), ("Coletas", sheader, sdata)], note)


@router.get("/trips/{trip_id}.pdf", summary="Relatório da viagem (PDF)")
def trip_pdf(trip_id: int, db: Session = Depends(get_db), user: User = Depends(require("leitura"))):
    t = db.get(Trip, trip_id)
    if not t:
        raise HTTPException(404, "viagem não encontrada")
    s = trip_summary(trip_id, db=db, _=user)
    alerts = db.scalars(select(Alert).where(Alert.trip_id == trip_id).order_by(Alert.first_seen_at)).all()
    samples = db.scalars(select(QualitySample).where(QualitySample.trip_id == trip_id)
                         .order_by(QualitySample.collected_at)).all()

    st = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=st["Heading1"], textColor=colors.HexColor("#0E2A22"))
    h2 = ParagraphStyle("h2", parent=st["Heading2"], textColor=colors.HexColor("#0E2A22"))
    body = st["BodyText"]
    small = ParagraphStyle("small", parent=body, fontSize=8, textColor=colors.HexColor("#52645E"))
    fmt = lambda d: d.astimezone(BR).strftime("%d/%m/%Y %H:%M") if d else "—"  # noqa: E731
    num = lambda v, u="": f"{v:.2f}{u}".replace(".", ",") if v is not None else "—"  # noqa: E731

    def table(rows, widths=None):
        tb = Table(rows, colWidths=widths, repeatRows=1)
        tb.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0E2A22")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#C9D3CF")), ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F4F6F5")]),
        ]))
        return tb

    story = [Paragraph(f"Relatório da viagem {t.code}", h1)]
    if t.is_simulated:
        story.append(Paragraph("<b>DADOS SIMULADOS</b> — gerados pelo simulador de hardware, não são leituras reais.",
                               ParagraphStyle("sim", parent=body, textColor=colors.HexColor("#2B347A"))))
    story += [
        table([["Campo", "Valor"],
               ["Status", t.status], ["Veículo", t.vehicle.plate], ["Motorista", t.driver.name],
               ["Origem", t.origin], ["Destino", t.destination],
               ["Saída", fmt(t.departure_at)], ["Chegada", fmt(t.arrival_at)],
               ["Duração", f"{s['duration_min']} min" if s["duration_min"] is not None else "—"],
               ["Volume", f"{t.volume_liters} L" if t.volume_liters else "—"],
               ["Última posição GPS", f"{s['last_gps']['lat']:.5f}, {s['last_gps']['lon']:.5f}" if s["last_gps"] else "—"]],
              [45 * mm, 120 * mm]),
        Spacer(1, 6 * mm), Paragraph("Qualidade medida", h2),
        table([["Indicador", "Valor"],
               ["Leituras válidas", str(s["readings_valid"])],
               ["Leituras inválidas ou sem horário", str(s["readings_invalid"])],
               ["Leituras que vieram da fila offline", str(s["readings_from_queue"])],
               ["pH médio (mín – máx)", f"{num(s['ph_avg'])} ({num(s['ph_min'])} – {num(s['ph_max'])})"],
               ["Temperatura do leite média / máxima", f"{num(s['milk_temp_avg'], ' °C')} / {num(s['milk_temp_max'], ' °C')}"],
               ["Acidez média das coletas", f"{s['acidity_avg']} °D".replace(".", ",") if s["acidity_avg"] else "—"],
               ["Coletas (recusadas)", f"{s['samples']} ({s['samples_rejected']})"]],
              [80 * mm, 85 * mm]),
        Spacer(1, 6 * mm), Paragraph("Coletas", h2),
    ]
    if samples:
        story.append(table([["Hora", "Produtor", "Acidez °D", "Densidade", "Volume L", "Decisão"]] + [
            [fmt(x.collected_at), Paragraph(x.producer, small),
             num(float(x.acidity_dornic) if x.acidity_dornic is not None else None),
             f"{x.density}" if x.density else "—", str(x.volume_liters or "—"), x.decision] for x in samples]))
    else:
        story.append(Paragraph("Nenhuma coleta registrada.", body))
    story += [Spacer(1, 6 * mm), Paragraph("Alertas", h2)]
    if alerts:
        story.append(table([["Início", "Severidade", "Alerta", "Status", "Ocorr."]] + [
            [fmt(a.first_seen_at), a.severity, Paragraph(a.title, small), a.status, str(a.occurrences)]
            for a in alerts], [30 * mm, 22 * mm, 80 * mm, 22 * mm, 14 * mm]))
    else:
        story.append(Paragraph("Nenhum alerta nesta viagem.", body))
    story += [Spacer(1, 8 * mm), Paragraph(
        f"Gerado em {datetime.now(UTC).astimezone(BR):%d/%m/%Y %H:%M} pelo LogLacto. "
        "Médias calculadas só com leituras válidas. Horários no fuso de Brasília.", small)]

    buf = io.BytesIO()
    SimpleDocTemplate(buf, pagesize=A4, title=f"Viagem {t.code}", leftMargin=18 * mm, rightMargin=18 * mm,
                      topMargin=16 * mm, bottomMargin=16 * mm).build(story)
    buf.seek(0)
    return StreamingResponse(buf, media_type="application/pdf",
                             headers={"Content-Disposition": f'attachment; filename="viagem-{t.code}.pdf"'})

