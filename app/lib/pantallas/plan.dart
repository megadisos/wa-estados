import 'package:flutter/material.dart';

import '../api.dart';
import '../comun.dart';

/// Próxima ejecución: qué servicios y productos salen, con opción de cambiarlos, quitarlos u ordenarlos.
class PantallaPlan extends StatefulWidget {
  const PantallaPlan({super.key, required this.api});

  final Api api;

  @override
  State<PantallaPlan> createState() => _PantallaPlanState();
}

class _PantallaPlanState extends State<PantallaPlan> {
  Map<String, dynamic>? _plan;
  Object? _error;
  String? _fecha; // null = la próxima que toca
  List<Map<String, dynamic>> _items = [];
  bool _cambios = false;
  bool _ocupado = false;

  @override
  void initState() {
    super.initState();
    _cargar();
  }

  Future<void> _cargar() async {
    setState(() => _error = null);
    try {
      final p = await widget.api.plan(fecha: _fecha);
      if (!mounted) return;
      setState(() {
        _plan = p;
        _items = [for (final i in (p['items'] as List? ?? [])) Map<String, dynamic>.from(i)];
        _cambios = false;
      });
    } catch (e) {
      if (mounted) setState(() => _error = e);
    }
  }

  Future<void> _ocupar(Future<void> Function() f) async {
    setState(() => _ocupado = true);
    try {
      await f();
    } catch (e) {
      if (mounted) avisar(context, e, error: true);
    } finally {
      if (mounted) setState(() => _ocupado = false);
    }
  }

  Future<void> _crear() => _ocupar(() async {
        final p = await widget.api.crearPlan(_plan!['fecha']);
        if (!mounted) return;
        setState(() {
          _plan = p;
          _items = [for (final i in (p['items'] as List? ?? [])) Map<String, dynamic>.from(i)];
          _cambios = false;
        });
        avisar(context, 'Plan creado. Ahora puedes cambiarlo.');
      });

  Future<void> _guardar() => _ocupar(() async {
        final p = await widget.api.cambiarPlan(_plan!['fecha'], [for (final i in _items) i['id'].toString()]);
        if (!mounted) return;
        setState(() {
          _plan = p;
          _items = [for (final i in (p['items'] as List? ?? [])) Map<String, dynamic>.from(i)];
          _cambios = false;
        });
        avisar(context, 'Plan guardado');
      });

  Future<void> _elegirFecha() async {
    final hoy = DateTime.now();
    final d = await showDatePicker(
      context: context,
      firstDate: hoy.subtract(const Duration(days: 13)),
      lastDate: hoy.add(const Duration(days: 30)),
      initialDate: DateTime.tryParse(_plan?['fecha'] ?? '') ?? hoy,
      helpText: 'Ver el plan del día',
    );
    if (d == null) return;
    setState(() => _fecha = isoFecha(d));
    await _cargar();
  }

  bool _publicado(Map<String, dynamic> it) => (it['publicado'] as Map? ?? {}).isNotEmpty;

  Future<void> _agregar({int? reemplazar}) async {
    final tipoInicial = reemplazar != null ? _items[reemplazar]['tipo'] as String? : null;
    final elegido = await Navigator.push<Map<String, dynamic>>(
      context,
      MaterialPageRoute(
        builder: (_) => SelectorCatalogo(
          api: widget.api,
          tipoInicial: tipoInicial == 'servicio' ? 'servicio' : 'producto',
          yaElegidos: {for (final i in _items) i['id'].toString()},
        ),
      ),
    );
    if (elegido == null) return;
    setState(() {
      final nuevo = {...elegido, 'publicado': <String, dynamic>{}, 'nuevo': false};
      if (reemplazar != null) {
        _items[reemplazar] = nuevo;
      } else {
        _items.add(nuevo);
      }
      _cambios = true;
    });
  }

  Future<void> _incierto(Map<String, dynamic> it, String cuenta) async {
    final accion = await showDialog<String>(
      context: context,
      builder: (c) => AlertDialog(
        title: const Text('Estado sin confirmar'),
        content: Text('En "$cuenta" se dio clic en Enviar pero no se pudo confirmar que "${it['titulo']}" '
            'quedara publicado. Revisa en el celular y dime qué pasó.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(c), child: const Text('Cancelar')),
          TextButton(onPressed: () => Navigator.pop(c, 'reintentar'), child: const Text('No salió: reintentar')),
          FilledButton(onPressed: () => Navigator.pop(c, 'ok'), child: const Text('Sí salió')),
        ],
      ),
    );
    if (accion == null) return;
    await _ocupar(() async {
      await widget.api.resolverIncierto(_plan!['fecha'], cuenta, it['id'], accion);
      await _cargar();
      if (mounted) {
        avisar(context, accion == 'ok' ? 'Marcado como publicado' : 'Se publicará en la próxima ejecución del día');
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final p = _plan;
    return Scaffold(
      appBar: AppBar(
        title: Text(p == null ? 'Próxima ejecución' : 'Plan del ${fechaBonita(p['fecha'])}'),
        actions: [
          IconButton(onPressed: _elegirFecha, icon: const Icon(Icons.calendar_month), tooltip: 'Otro día'),
          IconButton(
            onPressed: () async {
              if (_cambios && !await confirmar(context, 'Descartar cambios', '¿Descartar los cambios sin guardar?')) {
                return;
              }
              setState(() => _fecha = null);
              await _cargar();
            },
            icon: const Icon(Icons.refresh),
            tooltip: 'Volver a la próxima',
          ),
        ],
      ),
      floatingActionButton: _cambios
          ? FloatingActionButton.extended(
              onPressed: _ocupado ? null : _guardar,
              icon: const Icon(Icons.save),
              label: const Text('Guardar cambios'),
            )
          : null,
      body: _error != null && p == null
          ? ErrorConReintento(_error!, _cargar)
          : p == null
              ? const Cargando()
              : Stack(children: [
                  _cuerpo(context, p),
                  if (_ocupado) const LinearProgressIndicator(),
                ]),
    );
  }

  Widget _cuerpo(BuildContext context, Map<String, dynamic> p) {
    final t = Theme.of(context).textTheme;
    if (p['existe'] != true) {
      return ListView(padding: const EdgeInsets.all(24), children: [
        const Icon(Icons.event_available, size: 64),
        const SizedBox(height: 12),
        Text('El plan del ${fechaBonita(p['fecha'])} todavía no está armado', style: t.titleMedium, textAlign: TextAlign.center),
        const SizedBox(height: 8),
        const Text(
          'Se arma solo al publicar. Si lo creas ahora, el PC elige los servicios y productos que tocan según la rotación '
          'y luego puedes cambiarlos, quitarlos o agregar otros.',
          textAlign: TextAlign.center,
        ),
        const SizedBox(height: 20),
        Center(
          child: FilledButton.icon(
            onPressed: _ocupado ? null : _crear,
            icon: const Icon(Icons.auto_awesome),
            label: const Text('Crear plan ahora'),
          ),
        ),
      ]);
    }
    final pasado = (p['fecha'] as String).compareTo(isoFecha(DateTime.now())) < 0;
    final promoAct = p['promo_activa'] == true;
    return ListView(
      padding: const EdgeInsets.only(bottom: 96),
      children: [
        if (promoAct && p['promo_incluida'] != true)
          const ListTile(
            leading: Miniatura('', tipo: 'promo'),
            title: Text('Promo de la semana'),
            subtitle: Text('Se detecta sola en customania.com.co/promos al publicar'),
          ),
        ReorderableListView.builder(
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          buildDefaultDragHandles: !pasado,
          itemCount: _items.length,
          onReorderItem: (a, b) => setState(() {
            _items.insert(b, _items.removeAt(a));
            _cambios = true;
          }),
          itemBuilder: (context, i) => _fila(context, i, pasado),
        ),
        if (!pasado)
          Padding(
            padding: const EdgeInsets.all(16),
            child: OutlinedButton.icon(
              onPressed: _ocupado ? null : () => _agregar(),
              icon: const Icon(Icons.add),
              label: const Text('Agregar servicio o producto'),
            ),
          ),
        if (p['editado'] == true)
          const Padding(
            padding: EdgeInsets.symmetric(horizontal: 16),
            child: Text('Este plan fue cambiado desde la app.', textAlign: TextAlign.center),
          ),
      ],
    );
  }

  Widget _fila(BuildContext context, int i, bool pasado) {
    final it = _items[i];
    final cs = Theme.of(context).colorScheme;
    final pub = Map<String, dynamic>.from(it['publicado'] ?? {});
    final automatico = it['tipo'] == 'promo' || it['tipo'] == 'fijo';
    final bloqueado = pasado || automatico || _publicado(it);
    return ListTile(
      key: ValueKey(it['id']),
      leading: Miniatura(it['imagen']?.toString() ?? '', tipo: it['tipo']?.toString() ?? ''),
      title: Text(it['titulo']?.toString() ?? it['id'].toString(), maxLines: 2, overflow: TextOverflow.ellipsis),
      subtitle: Wrap(spacing: 6, runSpacing: 2, crossAxisAlignment: WrapCrossAlignment.center, children: [
        Text([etiquetaTipo(it['tipo']?.toString() ?? ''), if ((it['precio'] ?? '') != '') it['precio']].join(' · ')),
        if (it['nuevo'] == true) _chip('Nuevo', cs.tertiaryContainer, cs.onTertiaryContainer),
        for (final e in pub.entries)
          GestureDetector(
            onTap: e.value == 'incierto' ? () => _incierto(it, e.key) : null,
            child: e.value == 'ok'
                ? _chip('✓ ${e.key}', cs.primaryContainer, cs.onPrimaryContainer)
                : _chip('? ${e.key}', cs.errorContainer, cs.onErrorContainer),
          ),
      ]),
      trailing: bloqueado
          ? null
          : PopupMenuButton<String>(
              onSelected: (v) {
                if (v == 'cambiar') _agregar(reemplazar: i);
                if (v == 'quitar') {
                  setState(() {
                    _items.removeAt(i);
                    _cambios = true;
                  });
                }
              },
              itemBuilder: (_) => const [
                PopupMenuItem(value: 'cambiar', child: Text('Cambiar por otro')),
                PopupMenuItem(value: 'quitar', child: Text('Quitar')),
              ],
            ),
    );
  }

  Widget _chip(String texto, Color fondo, Color letra) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 1),
        decoration: BoxDecoration(color: fondo, borderRadius: BorderRadius.circular(6)),
        child: Text(texto, style: TextStyle(fontSize: 11, color: letra)),
      );
}

/// Lista del catálogo para elegir un servicio o producto, con búsqueda y filtro por categoría.
class SelectorCatalogo extends StatefulWidget {
  const SelectorCatalogo({super.key, required this.api, required this.tipoInicial, required this.yaElegidos});

  final Api api;
  final String tipoInicial;
  final Set<String> yaElegidos;

  @override
  State<SelectorCatalogo> createState() => _SelectorCatalogoState();
}

class _SelectorCatalogoState extends State<SelectorCatalogo> {
  Map<String, dynamic>? _cat;
  Object? _error;
  late String _tipo = widget.tipoInicial;
  String _buscar = '';
  String? _categoria;

  @override
  void initState() {
    super.initState();
    _cargar();
  }

  Future<void> _cargar({bool refrescar = false}) async {
    setState(() => _error = null);
    try {
      final c = await widget.api.catalogo(refrescar: refrescar);
      if (mounted) setState(() => _cat = c);
    } catch (e) {
      if (mounted) setState(() => _error = e);
    }
  }

  @override
  Widget build(BuildContext context) {
    final todos = [for (final i in (_cat?[_tipo] as List? ?? [])) Map<String, dynamic>.from(i)];
    final categorias = <String>{
      for (final i in todos)
        for (final c in (i['categorias'] as List? ?? [])) c.toString()
    }.toList()
      ..sort();
    final q = _buscar.toLowerCase();
    final lista = todos
        .where((i) => q.isEmpty || i['titulo'].toString().toLowerCase().contains(q))
        .where((i) => _categoria == null || (i['categorias'] as List? ?? []).contains(_categoria))
        .toList();
    return Scaffold(
      appBar: AppBar(
        title: const Text('Elegir del catálogo'),
        actions: [
          IconButton(onPressed: () => _cargar(refrescar: true), icon: const Icon(Icons.refresh), tooltip: 'Actualizar'),
        ],
      ),
      body: Column(children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(12, 8, 12, 0),
          child: SegmentedButton<String>(
            segments: const [
              ButtonSegment(value: 'servicio', label: Text('Servicios')),
              ButtonSegment(value: 'producto', label: Text('Productos')),
            ],
            selected: {_tipo},
            onSelectionChanged: (s) => setState(() {
              _tipo = s.first;
              _categoria = null;
            }),
          ),
        ),
        Padding(
          padding: const EdgeInsets.all(12),
          child: TextField(
            decoration: const InputDecoration(
              prefixIcon: Icon(Icons.search),
              hintText: 'Buscar',
              border: OutlineInputBorder(),
              isDense: true,
            ),
            onChanged: (v) => setState(() => _buscar = v),
          ),
        ),
        if (categorias.isNotEmpty)
          SizedBox(
            height: 40,
            child: ListView(scrollDirection: Axis.horizontal, padding: const EdgeInsets.symmetric(horizontal: 12), children: [
              Padding(
                padding: const EdgeInsets.only(right: 6),
                child: ChoiceChip(
                  label: const Text('Todas'),
                  selected: _categoria == null,
                  onSelected: (_) => setState(() => _categoria = null),
                ),
              ),
              for (final c in categorias)
                Padding(
                  padding: const EdgeInsets.only(right: 6),
                  child: ChoiceChip(
                    label: Text(c),
                    selected: _categoria == c,
                    onSelected: (_) => setState(() => _categoria = c),
                  ),
                ),
            ]),
          ),
        Expanded(
          child: _cat == null
              ? (_error != null ? ErrorConReintento(_error!, _cargar) : const Cargando())
              : lista.isEmpty
                  ? const Center(child: Text('Nada coincide'))
                  : ListView.builder(
                      itemCount: lista.length,
                      itemBuilder: (c, i) {
                        final it = lista[i];
                        final ya = widget.yaElegidos.contains(it['id']);
                        return ListTile(
                          enabled: !ya,
                          leading: Miniatura(it['imagen']?.toString() ?? '', tipo: _tipo),
                          title: Text(it['titulo'].toString()),
                          subtitle: Text(ya
                              ? 'Ya está en el plan'
                              : [if ((it['precio'] ?? '') != '') it['precio'], ...(it['categorias'] as List? ?? [])]
                                  .join(' · ')),
                          onTap: ya ? null : () => Navigator.pop(context, it),
                        );
                      },
                    ),
        ),
      ]),
    );
  }
}
