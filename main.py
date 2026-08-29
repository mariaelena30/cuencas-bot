"""
        **datos.model_dump(),
        "estado": "PENDIENTE",
        "unidad_asignada": None,
        "notas_despacho": None,
    }
    if supabase:
        supabase.table("sos_tickets").insert(ticket).execute()
    else:
        tickets_sos.insert(0, ticket)
    return {"ok": True, "ticket": ticket}


@app.get("/sos")
def listar_solicitudes_sos():
    if supabase:
        resultado = (
            supabase.table("sos_tickets")
            .select("*")
            .order("created_at", desc=True)
            .execute()
        )
        return {"tickets": resultado.data}
    return {"tickets": tickets_sos}


@app.patch("/sos/{ticket_id}")
def actualizar_solicitud_sos(ticket_id: str, datos: ActualizacionSOS):
    cambios = {"estado": datos.estado}
    if datos.unidad_asignada is not None:
        cambios["unidad_asignada"] = datos.unidad_asignada
    if datos.notas_despacho is not None:
        cambios["notas_despacho"] = datos.notas_despacho

    if supabase:
        resultado = (
            supabase.table("sos_tickets").update(cambios).eq("id", ticket_id).execute()
        )
        if not resultado.data:
            return {"error": f"Ticket '{ticket_id}' no encontrado"}
        return {"ok": True, "ticket": resultado.data[0]}

    ticket = next((t for t in tickets_sos if t["id"] == ticket_id), None)
    if ticket is None:
        return {"error": f"Ticket '{ticket_id}' no encontrado"}
    ticket.update(cambios)
    return {"ok": True, "ticket": ticket}


@app.post("/reportes")
def crear_reporte_ciudadano(datos: ReporteCiudadano):
    if datos.localidad.lower() not in localidades:
        return {"error": f"Localidad '{datos.localidad}' no reconocida"}
    reporte = {
        "id": f"rep_{int(datetime.now(timezone.utc).timestamp() * 1000)}",
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        **datos.model_dump(),
    }
    if supabase:
        supabase.table("reportes_ciudadanos").insert(reporte).execute()
    else:
        reportes_ciudadanos.insert(0, reporte)
    return {"ok": True, "reporte": reporte}


@app.get("/reportes")
def listar_reportes_ciudadanos():
    if supabase:
        resultado = (
            supabase.table("reportes_ciudadanos")
            .select("*")
            .order("created_at", desc=True)
            .execute()
        )
        return {"reportes": resultado.data}
    return {"reportes": reportes_ciudadanos}


from whatsapp_webhook import router as whatsapp_router
app.include_router(whatsapp_router)
