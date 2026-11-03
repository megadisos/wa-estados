import 'dart:async';

import 'package:flutter/material.dart';

import '../api.dart';
import '../comun.dart';

class PantallaInicio extends StatefulWidget {
  const PantallaInicio({super.key, required this.api, required this.irA});

  final Api api;
  final void Function(int) irA;

  @override
  State<PantallaInicio> createState() => _PantallaInicioState();
}

class _PantallaInicioState extends State<PantallaInicio> {
  Map<String, dynamic>? _e;
  Object? _error;
  Timer? _timer;
  bool _ocupado = false;

  @override
  void initState() {
    super.initState();
    _cargar();
    _timer = Timer.periodic(const Duration(seconds: 5), (_) => _cargar(silencioso: true));
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  Future<void> _cargar({bool silencioso = false}) async {
    try {
      final e = await widget.api.estado();
      if (mounted) {
        setState(() {
          _e = e;
          _error = null;
        });
      }
    } catch (e) {
      if (mounted && (!silencioso || _e == null)) setState(() => _error = e);
    }
  }

  Future<void> _accion(Future<dynamic> Function() f, {String? ok}) async {
    setState(() => _ocupado = true);
    try {
      final r = await f();
      if (!mounted) return;
      final msg = ok ?? (r is Map && r['mensaje'] != null ? r['mensaje'].toString() : 'Listo');
      avisar(context, msg);
      await _cargar();
    } catch (e) {
      if (mounted) avisar(context, e, error: true);
    } finally {
      if (mounted) setState(() => _ocupado = false);
    }
  }

  Future<void> _ejecutarAhora() async {
    final cuentas = [for (final c in (_e?['cuentas'] as List? ?? [])) c['nombre'].toString()];
    final opciones = await showModalBottomSheet<_OpcionesEjecucion>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (c) => _HojaEjecutar(cuentas: cuentas),
    );
    if (opciones == null) return;
    await _accion(
      () => widget.api.ejecutar(
        real: opciones.real,
        cuenta: opciones.cuenta,
        ignorarHorario: opciones.ignorarHorario,
        sinEspera: opciones.sinEspera,
      ),
      ok: opciones.real ? 'Publicación iniciada. Sigue el avance en Log.' : 'Prueba iniciada. Mira el resultado en Log.',
    );
  }

  Future<void> _detener() async {
    final forzar = await showDialog<bool>(
      context: context,
      builder: (c) => AlertDialog(
        title: const Text('Detener la ejecución'),
        content: const Text(
            'Detener: termina el estado que está subiendo y para.\n\n'
            'Forzar: corta ya mismo (puede quedar un estado a medias).'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(c), child: const Text('Cancelar')),
          TextButton(onPressed: () => Navigator.pop(c, true), child: const Text('Forzar')),
          FilledButton(onPressed: () => Navigator.pop(c, false), child: const Text('Detener')),
        ],
      ),
    );
    if (forzar == null) return;
    await _accion(() => widget.api.detener(forzar: forzar));
  }

  Future<void> _pausar() async {
    final pausado = _e?['pausado'] == true;
    if (pausado) {
      await _accion(() => widget.api.pausar(false), ok: 'Programación reanudada');
      return;
    }
    final eleccion = await showModalBottomSheet<String>(
      context: context,
      showDragHandle: true,
      builder: (c) => SafeArea(
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          const ListTile(
            title: Text('Pausar publicaciones programadas'),
            subtitle: Text('La tarea de las 5:00 a. m. no publicará. Puedes seguir usando "Ejecutar ahora".'),
          ),
          ListTile(
            leading: const Icon(Icons.pause_circle_outline),
            title: const Text('Hasta que la reanude'),
            onTap: () => Navigator.pop(c, ''),
          ),
          ListTile(
            leading: const Icon(Icons.today),
            title: const Text('Solo hoy'),
            onTap: () => Navigator.pop(c, isoFecha(DateTime.now())),
          ),
          ListTile(
            leading: const Icon(Icons.date_range),
            title: const Text('Hasta una fecha…'),
            onTap: () async {
              final hoy = DateTime.now();
              final d = await showDatePicker(
                context: c,
                firstDate: hoy,
                lastDate: hoy.add(const Duration(days: 365)),
                initialDate: hoy.add(const Duration(days: 1)),
                helpText: 'Pausar hasta (incluido)',
              );
              if (c.mounted) Navigator.pop(c, d == null ? null : isoFecha(d));
            },
          ),
        ]),
      ),
    );
    if (eleccion == null) return;
    await _accion(
      () => widget.api.pausar(true, hasta: eleccion.isEmpty ? null : eleccion),
      ok: eleccion.isEmpty ? 'Programación en pausa' : 'En pausa hasta el ${fechaBonita(eleccion)}',
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Estados WhatsApp'),
        actions: [IconButton(onPressed: _cargar, icon: const Icon(Icons.refresh))],
      ),
      body: _e == null
          ? (_error != null ? ErrorConReintento(_error!, _cargar) : const Cargando())
          : RefreshIndicator(onRefresh: _cargar, child: _contenido(context)),
    );
  }

  Widget _contenido(BuildContext context) {
    final e = _e!;
    final cs = Theme.of(context).colorScheme;
    final t = Theme.of(context).textTheme;
    final ej = Map<String, dynamic>.from(e['ejecucion'] ?? {});
    final enCurso = ej['en_curso'] == true;
    final pausado = e['pausado'] == true;
    final tarea = e['tarea_programada'] is Map ? Map<String, dynamic>.from(e['tarea_programada']) : null;

    final (IconData icono, Color color, String titulo, String sub) = enCurso
        ? (
            Icons.play_circle,
            Colors.blue,
            ej['deteniendo'] == true ? 'Deteniéndose…' : 'Publicando ahora',
            '${ej['modo'] == 'prueba' ? 'Modo prueba · ' : ''}${ej['publicados'] ?? 0} estados subidos desde ${fechaHora(ej['inicio'])}'
          )
        : pausado
            ? (
                Icons.pause_circle,
                Colors.orange,
                'En pausa',
                e['pausa_hasta'] != null
                    ? 'Se reanuda sola después del ${fechaBonita(e['pausa_hasta'])}'
                    : 'No se publicará hasta que la reanudes'
              )
            : (
                Icons.check_circle,
                Colors.green,
                'Activa',
                'Próxima publicación: ${fechaBonita(e['proxima_fecha'])}'
              );

    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Card(
          color: color.withValues(alpha: 0.12),
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Row(children: [
              Icon(icono, size: 48, color: color),
              const SizedBox(width: 16),
              Expanded(
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text(titulo, style: t.titleLarge),
                  const SizedBox(height: 4),
                  Text(sub),
                ]),
              ),
            ]),
          ),
        ),
        const SizedBox(height: 12),
        Wrap(spacing: 8, runSpacing: 8, children: [
          if (!enCurso)
            FilledButton.icon(
              onPressed: _ocupado ? null : _ejecutarAhora,
              icon: const Icon(Icons.play_arrow),
              label: const Text('Ejecutar ahora'),
            ),
          if (enCurso)
            FilledButton.icon(
              style: FilledButton.styleFrom(backgroundColor: cs.error, foregroundColor: cs.onError),
              onPressed: _ocupado ? null : _detener,
              icon: const Icon(Icons.stop),
              label: const Text('Detener'),
            ),
          FilledButton.tonalIcon(
            onPressed: _ocupado ? null : _pausar,
            icon: Icon(pausado ? Icons.play_circle_outline : Icons.pause),
            label: Text(pausado ? 'Reanudar programación' : 'Pausar programación'),
          ),
          if (enCurso)
            OutlinedButton.icon(
              onPressed: () => widget.irA(3),
              icon: const Icon(Icons.terminal),
              label: const Text('Ver log'),
            ),
        ]),
        const SizedBox(height: 16),
        Text('Hoy, ${fechaBonita(e['hoy']?['fecha'])}', style: t.titleMedium),
        const SizedBox(height: 4),
        Card(
          child: Column(children: [
            for (final c in (e['cuentas'] as List? ?? []))
              ListTile(
                leading: Icon(c['activa'] == true ? Icons.person : Icons.person_off_outlined),
                title: Text(c['nombre'].toString()),
                subtitle: Text(c['activa'] == true ? 'Activa' : 'Desactivada'),
                trailing: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  crossAxisAlignment: CrossAxisAlignment.end,
                  children: [
                    Text('${c['publicados_hoy']} / ${e['hoy']?['planificados'] ?? 0}', style: t.titleMedium),
                    if ((c['inciertos_hoy'] ?? 0) > 0)
                      Text('${c['inciertos_hoy']} sin confirmar', style: TextStyle(color: cs.error, fontSize: 12)),
                  ],
                ),
                onTap: () => widget.irA(1),
              ),
          ]),
        ),
        const SizedBox(height: 16),
        Text('Programación', style: t.titleMedium),
        const SizedBox(height: 4),
        Card(
          child: Column(children: [
            ListTile(
              leading: const Icon(Icons.schedule),
              title: Text(tarea == null
                  ? 'Tarea programada no encontrada'
                  : tarea['activa'] == true
                      ? 'Próxima: ${fechaHora(tarea['proxima'])}'
                      : 'Tarea programada desactivada en Windows'),
              subtitle: Text(tarea == null
                  ? 'Ejecuta activar_tarea.bat en el PC'
                  : 'Última: ${fechaHora(tarea['ultima'])}'),
            ),
            ListTile(
              leading: const Icon(Icons.shield_outlined),
              title: Text('Horario permitido: ${e['ventana']?[0]} a ${e['ventana']?[1]}'),
              subtitle: Text('Hora del PC: ${fechaHora(e['hora_pc'])}'),
            ),
            if (ej['inicio'] != null && !enCurso)
              ListTile(
                leading: Icon(_iconoResultado(ej['estado'])),
                title: Text('Última ejecución: ${_textoResultado(ej['estado'])}'),
                subtitle: Text('${fechaHora(ej['inicio'])} · ${ej['publicados'] ?? 0} estados'
                    '${ej['modo'] == 'prueba' ? ' · prueba' : ''}'
                    '${ej['origen'] == 'app' ? ' · desde la app' : ''}'),
                onTap: () => widget.irA(3),
              ),
          ]),
        ),
      ],
    );
  }

  IconData _iconoResultado(dynamic estado) => switch (estado) {
        'ok' => Icons.check_circle_outline,
        'detenida' || 'cancelada' => Icons.stop_circle_outlined,
        _ => Icons.error_outline,
      };

  String _textoResultado(dynamic estado) => switch (estado) {
        'ok' => 'bien',
        'con_fallos' => 'con fallos',
        'detenida' => 'detenida',
        'cancelada' => 'cancelada',
        'interrumpida' => 'interrumpida',
        _ => estado?.toString() ?? '',
      };
}

class _OpcionesEjecucion {
  _OpcionesEjecucion(this.real, this.cuenta, this.ignorarHorario, this.sinEspera);
  final bool real;
  final String? cuenta;
  final bool ignorarHorario;
  final bool sinEspera;
}

class _HojaEjecutar extends StatefulWidget {
  const _HojaEjecutar({required this.cuentas});
  final List<String> cuentas;

  @override
  State<_HojaEjecutar> createState() => _HojaEjecutarState();
}

class _HojaEjecutarState extends State<_HojaEjecutar> {
  bool _real = true;
  String? _cuenta;
  bool _ignorarHorario = false;
  bool _sinEspera = false;

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
        child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          Text('Ejecutar ahora', style: Theme.of(context).textTheme.titleLarge),
          const SizedBox(height: 12),
          SegmentedButton<bool>(
            segments: const [
              ButtonSegment(value: true, label: Text('Publicar'), icon: Icon(Icons.send)),
              ButtonSegment(value: false, label: Text('Solo prueba'), icon: Icon(Icons.science_outlined)),
            ],
            selected: {_real},
            onSelectionChanged: (s) => setState(() => _real = s.first),
          ),
          const SizedBox(height: 4),
          Text(
            _real
                ? 'Publica lo que falte del día en WhatsApp. Lo ya publicado no se repite.'
                : 'Arma el plan, los textos y las imágenes sin abrir WhatsApp.',
            style: Theme.of(context).textTheme.bodySmall,
          ),
          const SizedBox(height: 12),
          DropdownButtonFormField<String?>(
            initialValue: _cuenta,
            decoration: const InputDecoration(labelText: 'Cuenta', border: OutlineInputBorder()),
            items: [
              const DropdownMenuItem(value: null, child: Text('Todas las activas')),
              for (final c in widget.cuentas) DropdownMenuItem(value: c, child: Text(c)),
            ],
            onChanged: (v) => setState(() => _cuenta = v),
          ),
          if (_real) ...[
            SwitchListTile(
              contentPadding: EdgeInsets.zero,
              title: const Text('Ignorar el horario permitido'),
              subtitle: const Text('Publica aunque sea de noche'),
              value: _ignorarHorario,
              onChanged: (v) => setState(() => _ignorarHorario = v),
            ),
            SwitchListTile(
              contentPadding: EdgeInsets.zero,
              title: const Text('Sin pausas'),
              subtitle: const Text('Omite las pausas entre estados y cuentas. Es más rápido pero parece menos humano.'),
              value: _sinEspera,
              onChanged: (v) => setState(() => _sinEspera = v),
            ),
          ],
          const SizedBox(height: 12),
          FilledButton(
            onPressed: () => Navigator.pop(context, _OpcionesEjecucion(_real, _cuenta, _ignorarHorario, _sinEspera)),
            child: Text(_real ? 'Publicar ahora' : 'Probar'),
          ),
        ]),
      ),
    );
  }
}
