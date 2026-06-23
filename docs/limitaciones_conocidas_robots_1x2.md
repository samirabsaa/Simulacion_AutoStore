# Limitaciones conocidas — robots 1×2

## Livelock de coordinación a alta ocupación (turno diurno)

**Estado:** pendiente (diferido). No bloquea P1/P2 del rediseño 1×2 pero sí puede
impedir que los demos P09 completen el 100% de la ola a 78–90 % de ocupación.

### Síntoma
A ocupación alta (p. ej. escenario Forus 12×10×5, 78 %, 2N/3E/3O), la simulación
diurna **no completa siempre el 100 %** de la ola: típicamente alcanza 75–95 % y luego
entra en **livelock** (robots oscilando/bloqueados sin progreso). En casos puntuales el
estancamiento es temprano (un seed observado: 3/20 pedidos).

### Causas identificadas
1. **Menos puntos de entrega.** Las estaciones de salida E/O son `mitad(gy)` por lado
   (intercaladas), por diseño realista → más contención por estación y rutas más largas.
2. **Inanición de handoff (NORTE).** Un robot NORTE no entrega en estación: depende de
   ceder su caja a un E/O ocioso. Si todos los E/O están ocupados/atascados, el NORTE
   queda cargado bloqueando, y el bloqueo no se despeja por sí solo.
3. **Coordinación greedy.** El avance de robots por tick es por-robot (greedy) con
   desempates por id; produce oscilación bajo congestión.

### Por qué no se resolvió con heurísticas
Se probaron (aquí y en iteraciones previas): orden por prioridad, estaciones distintas,
reserva ligera, cesión proactiva, anti-inanición NORTE, reruta BFS. **No convergen** a
~100 %; varias empeoran (mueven el conflicto en vez de resolverlo).

### Solución recomendada (cuando se retome)
Planificación **cooperativa con reservas espacio-temporales** (WHCA* / planificación por
ventana): los robots se planifican de forma conjunta y coordinada por tick, no uno-a-uno.
Las estructuras `ReservationTable` y `WaitForGraph` de `motor/colmena.py` son el punto de
partida (hoy se siembran pero no se usan para mover). Conviene aplicarlo también al
`DespachadorNocturno` (mismo patrón de livelock a alta contención).

### Mitigaciones temporales para demos
Mientras no exista el planificador, los demos pueden hacerse tratables sin tocar la
lógica: más estaciones (no reducir a la mitad), menos robots, menor ocupación, o sin
robots NORTE en turno diurno (evita la dependencia de handoff).
