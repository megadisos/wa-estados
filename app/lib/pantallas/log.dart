import 'dart:async';

import 'package:flutter/material.dart';

import '../api.dart';
import '../comun.dart';

/// Log en vivo: consulta cada 2 segundos solo lo nuevo del archivo.
class PantallaLog extends StatefulWidget {
  const PantallaLog({super.key, required this.api, required this.visible});

  final Api api;
  final bool visible;

  @override
  State<PantallaLog> createState() => _PantallaLogState();
}

class _PantallaLogState extends State<PantallaLog> {
  static const _maxCaracteres = 200000;
  String _archivo = 'estados';
  String _texto = '';
  int _offset = -1;
  Object? _error;
  Timer? _timer;
  bool _seguir = true;
  bool _leyendo = false;
  final _scroll = ScrollController();

  @override
  void initState() {
    super.initState();
    _actualizarTimer();
  }

  @override
  void didUpdateWidget(PantallaLog old) {
    super.didUpdateWidget(old);
    if (old.visible != widget.visible) _actualizarTimer();
  }

  void _actualizarTimer() {
    _timer?.cancel();
    if (widget.visible) {
      _leer();
      _timer = Timer.periodic(const Duration(seconds: 2), (_) => _leer());
    }
  }

  @override
  void dispose() {
    _timer?.cancel();
    _scroll.dispose();
    super.dispose();
  }

  Future<void> _leer() async {
    if (_leyendo) return;
    _leyendo = true;
    try {
      final r = await widget.api.log(archivo: _archivo, desde: _offset);
      if (!mounted) return;
      final nuevo = r['texto']?.toString() ?? '';
      final offset = (r['offset'] as num?)?.toInt() ?? 0;
      final tamano = (r['tamano'] as num?)?.toInt() ?? 0;
      setState(() {
        _error = null;
        if (_offset >= 0 && tamano < _offset) {
          _texto = nuevo; // el archivo se reinició o rotó
        } else if (nuevo.isNotEmpty) {
          _texto += nuevo;
          if (_texto.length > _maxCaracteres) _texto = _texto.substring(_texto.length - _maxCaracteres);
        }
        _offset = offset;
      });
      if (nuevo.isNotEmpty && _seguir) {
        WidgetsBinding.instance.addPostFrameCallback((_) {
          if (_scroll.hasClients) _scroll.jumpTo(_scroll.position.maxScrollExtent);
        });
      }
    } catch (e) {
      if (mounted) setState(() => _error = e);
    } finally {
      _leyendo = false;
    }
  }

  void _cambiarArchivo(String a) {
    setState(() {
      _archivo = a;
      _texto = '';
      _offset = -1;
    });
    _leer();
  }

  Color? _color(String linea, ColorScheme cs) {
    if (linea.contains(' ERROR ') || linea.contains('ALERTA')) return cs.error;
    if (linea.contains(' WARNING ')) return Colors.orange;
    if (linea.contains('Publicando') || linea.contains('Listo')) return cs.primary;
    return null;
  }

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final lineas = _texto.split('\n');
    return Scaffold(
      appBar: AppBar(
        title: const Text('Log'),
        actions: [
          IconButton(
            tooltip: _seguir ? 'Dejar de seguir' : 'Seguir el final',
            icon: Icon(_seguir ? Icons.vertical_align_bottom : Icons.pause),
            onPressed: () => setState(() => _seguir = !_seguir),
          ),
        ],
        bottom: PreferredSize(
          preferredSize: const Size.fromHeight(52),
          child: Padding(
            padding: const EdgeInsets.only(bottom: 8),
            child: SegmentedButton<String>(
              segments: const [
                ButtonSegment(value: 'estados', label: Text('Registro general')),
                ButtonSegment(value: 'salida', label: Text('Última ejecución')),
              ],
              selected: {_archivo},
              onSelectionChanged: (s) => _cambiarArchivo(s.first),
            ),
          ),
        ),
      ),
      body: Column(children: [
        if (_error != null)
          MaterialBanner(
            content: Text(_error.toString()),
            actions: [TextButton(onPressed: _leer, child: const Text('Reintentar'))],
          ),
        Expanded(
          child: _texto.isEmpty && _error == null
              ? (_offset < 0 ? const Cargando() : const Center(child: Text('El log está vacío')))
              : Container(
                  color: cs.surfaceContainerLowest,
                  child: ListView.builder(
                    controller: _scroll,
                    padding: const EdgeInsets.all(8),
                    itemCount: lineas.length,
                    itemBuilder: (c, i) => SelectableText(
                      lineas[i],
                      style: TextStyle(fontFamily: 'monospace', fontSize: 11.5, color: _color(lineas[i], cs)),
                    ),
                  ),
                ),
        ),
      ]),
    );
  }
}
