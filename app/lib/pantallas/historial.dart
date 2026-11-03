import 'package:flutter/material.dart';

import '../api.dart';
import '../comun.dart';

class PantallaHistorial extends StatefulWidget {
  const PantallaHistorial({super.key, required this.api});

  final Api api;

  @override
  State<PantallaHistorial> createState() => _PantallaHistorialState();
}

class _PantallaHistorialState extends State<PantallaHistorial> {
  List<Map<String, dynamic>>? _filas;
  Object? _error;
  String? _cuenta;
  int _dias = 30;

  @override
  void initState() {
    super.initState();
    _cargar();
  }

  Future<void> _cargar() async {
    setState(() => _error = null);
    try {
      final h = await widget.api.historial(dias: _dias, cuenta: _cuenta);
      if (mounted) setState(() => _filas = [for (final f in h) Map<String, dynamic>.from(f)]);
    } catch (e) {
      if (mounted) setState(() => _error = e);
    }
  }

  @override
  Widget build(BuildContext context) {
    final filas = _filas;
    final cuentas = <String>{for (final f in filas ?? []) f['cuenta'].toString()}.toList()..sort();
    return Scaffold(
      appBar: AppBar(
        title: const Text('Lo que se publicó'),
        actions: [
          PopupMenuButton<int>(
            icon: const Icon(Icons.filter_list),
            tooltip: 'Periodo',
            initialValue: _dias,
            onSelected: (d) {
              setState(() => _dias = d);
              _cargar();
            },
            itemBuilder: (_) => const [
              PopupMenuItem(value: 7, child: Text('Últimos 7 días')),
              PopupMenuItem(value: 30, child: Text('Últimos 30 días')),
              PopupMenuItem(value: 90, child: Text('Últimos 90 días')),
              PopupMenuItem(value: 3650, child: Text('Todo')),
            ],
          ),
        ],
      ),
      body: filas == null
          ? (_error != null ? ErrorConReintento(_error!, _cargar) : const Cargando())
          : RefreshIndicator(
              onRefresh: _cargar,
              child: ListView(children: [
                if (cuentas.length > 1 || _cuenta != null)
                  Padding(
                    padding: const EdgeInsets.fromLTRB(12, 8, 12, 0),
                    child: Wrap(spacing: 6, children: [
                      ChoiceChip(
                        label: const Text('Todas'),
                        selected: _cuenta == null,
                        onSelected: (_) {
                          setState(() => _cuenta = null);
                          _cargar();
                        },
                      ),
                      for (final c in {...cuentas, ?_cuenta})
                        ChoiceChip(
                          label: Text(c),
                          selected: _cuenta == c,
                          onSelected: (_) {
                            setState(() => _cuenta = c);
                            _cargar();
                          },
                        ),
                    ]),
                  ),
                if (filas.isEmpty)
                  const Padding(
                    padding: EdgeInsets.all(32),
                    child: Text(
                      'Todavía no hay publicaciones registradas. El historial empieza a llenarse con la primera '
                      'publicación hecha con esta versión.',
                      textAlign: TextAlign.center,
                    ),
                  ),
                ..._agrupado(context, filas),
              ]),
            ),
    );
  }

  List<Widget> _agrupado(BuildContext context, List<Map<String, dynamic>> filas) {
    final t = Theme.of(context).textTheme;
    final cs = Theme.of(context).colorScheme;
    final out = <Widget>[];
    String? fecha;
    for (final f in filas) {
      if (f['fecha'] != fecha) {
        fecha = f['fecha'];
        final n = filas.where((x) => x['fecha'] == fecha && x['resultado'] == 'ok').length;
        out.add(Padding(
          padding: const EdgeInsets.fromLTRB(16, 16, 16, 4),
          child: Text('${fechaBonita(fecha)} · $n publicados', style: t.titleSmall),
        ));
      }
      final ok = f['resultado'] == 'ok';
      out.add(ListTile(
        leading: Miniatura(f['imagen']?.toString() ?? '', tipo: f['tipo']?.toString() ?? ''),
        title: Text(f['titulo']?.toString() ?? f['id'].toString(), maxLines: 2, overflow: TextOverflow.ellipsis),
        subtitle: Text('${etiquetaTipo(f['tipo']?.toString() ?? '')} · ${f['cuenta']} · ${fechaHora(f['hora'])}'
            '${f['origen'] == 'app' ? ' · desde la app' : ''}'),
        trailing: ok
            ? Icon(Icons.check_circle, color: cs.primary)
            : Tooltip(message: 'Sin confirmar', child: Icon(Icons.help, color: cs.error)),
      ));
    }
    return out;
  }
}
