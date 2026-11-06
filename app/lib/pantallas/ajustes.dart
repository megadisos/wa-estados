import 'package:flutter/material.dart';

import '../api.dart';
import '../comun.dart';
import 'conexion.dart';

class PantallaAjustes extends StatefulWidget {
  const PantallaAjustes({super.key, required this.api, required this.alCambiarConexion});

  final Api api;
  final void Function(Api?) alCambiarConexion;

  @override
  State<PantallaAjustes> createState() => _PantallaAjustesState();
}

class _PantallaAjustesState extends State<PantallaAjustes> {
  Map<String, dynamic>? _a;
  Object? _error;
  bool _guardando = false;

  @override
  void initState() {
    super.initState();
    _cargar();
  }

  Future<void> _cargar() async {
    setState(() => _error = null);
    try {
      final a = await widget.api.ajustes();
      if (mounted) setState(() => _a = a);
    } catch (e) {
      if (mounted) setState(() => _error = e);
    }
  }

  Future<void> _guardar(Map<String, dynamic> cambios, {String ok = 'Guardado'}) async {
    setState(() => _guardando = true);
    try {
      final a = await widget.api.guardarAjustes(cambios);
      if (!mounted) return;
      setState(() => _a = a);
      avisar(context, ok);
    } catch (e) {
      if (mounted) avisar(context, e, error: true);
    } finally {
      if (mounted) setState(() => _guardando = false);
    }
  }

  List<String> _lista(String k) => [for (final x in (_a?[k] as List? ?? [])) x.toString()];

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Ajustes'),
        bottom: _guardando
            ? const PreferredSize(preferredSize: Size.fromHeight(4), child: LinearProgressIndicator())
            : null,
      ),
      body: _a == null
          ? (_error != null ? ErrorConReintento(_error!, _cargar) : const Cargando())
          : RefreshIndicator(onRefresh: _cargar, child: _contenido(context)),
    );
  }

  Widget _titulo(String t) => Padding(
        padding: const EdgeInsets.fromLTRB(16, 20, 16, 4),
        child: Text(t, style: Theme.of(context).textTheme.titleSmall?.copyWith(color: Theme.of(context).colorScheme.primary)),
      );

  Widget _contenido(BuildContext context) {
    final a = _a!;
    final promo = Map<String, dynamic>.from(a['promo_semana'] ?? {});
    final cuentas = Map<String, dynamic>.from(a['cuentas_activas'] ?? {});
    final exclCat = _lista('excluir_categorias');
    final exclPal = _lista('excluir_productos');
    final exclServ = _lista('excluir_servicios');
    return ListView(padding: const EdgeInsets.only(bottom: 32), children: [
      _titulo('Cuántos estados por día'),
      _Contador(
        titulo: 'Servicios por día',
        valor: (a['servicios_por_dia'] as num?)?.toInt() ?? 3,
        alCambiar: (v) => _guardar({'servicios_por_dia': v}),
      ),
      _Contador(
        titulo: 'Productos por día',
        valor: (a['productos_por_dia'] as num?)?.toInt() ?? 3,
        alCambiar: (v) => _guardar({'productos_por_dia': v}),
      ),
      const Padding(
        padding: EdgeInsets.symmetric(horizontal: 16),
        child: Text('Aplica a los planes que se armen desde ahora. Más estados al día aumentan el riesgo de bloqueo.',
            style: TextStyle(fontSize: 12)),
      ),
      _titulo('Cuentas'),
      for (final e in cuentas.entries)
        SwitchListTile(
          title: Text(e.key),
          subtitle: Text(e.value == true ? 'Publica' : 'No publica'),
          value: e.value == true,
          onChanged: (v) => _guardar({
            'cuentas_activas': {e.key: v}
          }),
        ),
      _titulo('Promo de la semana'),
      SwitchListTile(
        title: const Text('Publicar la promo de la semana'),
        value: promo['activa'] != false,
        onChanged: (v) => _guardar({
          'promo_semana': {'activa': v}
        }),
      ),
      ListTile(
        title: const Text('Posición'),
        trailing: SegmentedButton<String>(
          segments: const [
            ButtonSegment(value: 'primero', label: Text('Primero')),
            ButtonSegment(value: 'ultimo', label: Text('Último')),
          ],
          selected: {promo['posicion']?.toString() == 'ultimo' ? 'ultimo' : 'primero'},
          onSelectionChanged: (s) => _guardar({
            'promo_semana': {'posicion': s.first}
          }),
        ),
      ),
      ListTile(
        title: const Text('Fijar una promo a mano'),
        subtitle: Text((promo['forzar'] ?? '').toString().isEmpty
            ? 'Automática (se detecta sola)'
            : 'Fijada: ${promo['forzar']}  (recuerda quitarla la otra semana)'),
        trailing: const Icon(Icons.edit),
        onTap: () async {
          final v = await _pedirTexto(context, 'Promo fijada', 'Slug o URL de la promo. Vacío = automática',
              (promo['forzar'] ?? '').toString());
          if (v != null) {
            await _guardar({
              'promo_semana': {'forzar': v.trim()}
            });
          }
        },
      ),
      ListTile(
        leading: const Icon(Icons.search),
        title: const Text('Ver qué promo detecta ahora'),
        onTap: () async {
          avisar(context, 'Revisando customania.com.co/promos…');
          try {
            final p = await widget.api.promo();
            if (!context.mounted) return;
            await showDialog<void>(
              context: context,
              builder: (c) => AlertDialog(
                title: const Text('Promo de la semana'),
                content: Column(mainAxisSize: MainAxisSize.min, children: [
                  if ((p['imagen'] ?? '').toString().isNotEmpty)
                    ClipRRect(
                      borderRadius: BorderRadius.circular(8),
                      child: Image.network(p['imagen'].toString(), height: 200, errorBuilder: (_, _, _) => const SizedBox()),
                    ),
                  const SizedBox(height: 8),
                  Text(p['titulo']?.toString() ?? ''),
                  Text(p['url']?.toString() ?? '', style: const TextStyle(fontSize: 12)),
                ]),
                actions: [TextButton(onPressed: () => Navigator.pop(c), child: const Text('Cerrar'))],
              ),
            );
          } catch (e) {
            if (context.mounted) avisar(context, e, error: true);
          }
        },
      ),
      _titulo('Estados fijos (salen todos los días)'),
      if ((a['fijos'] as List? ?? []).isEmpty)
        const ListTile(subtitle: Text('No hay estados fijos en config.toml')),
      for (final f in [for (final x in (a['fijos'] as List? ?? [])) Map<String, dynamic>.from(x)]) ...[
        SwitchListTile(
          secondary: Miniatura(f['imagen']?.toString() ?? '', tipo: 'fijo'),
          title: Text(f['titulo']?.toString() ?? f['id'].toString()),
          subtitle: Text(f['url']?.toString() ?? '', maxLines: 1, overflow: TextOverflow.ellipsis),
          value: f['activo'] == true,
          onChanged: (v) => _guardar({
            'fijos': {
              f['id']: {'activo': v}
            }
          }),
        ),
        ListTile(
          contentPadding: const EdgeInsets.only(left: 88, right: 16),
          title: const Text('Texto del estado'),
          subtitle: Text((f['texto'] ?? '').toString(), maxLines: 3, overflow: TextOverflow.ellipsis),
          trailing: const Icon(Icons.edit),
          onTap: () async {
            final v = await _pedirTexto(context, 'Texto de ${f['titulo']}', 'Datos: {titulo} {url} {wa}',
                (f['texto'] ?? '').toString(),
                lineas: 5);
            if (v != null) {
              await _guardar({
                'fijos': {
                  f['id']: {'texto': v}
                }
              });
            }
          },
        ),
      ],
      _titulo('Restricciones'),
      ListTile(
        leading: const Icon(Icons.category_outlined),
        title: const Text('Categorías de productos'),
        subtitle: Text(exclCat.isEmpty ? 'Se publican todas' : 'Excluidas: ${exclCat.join(', ')}'),
        trailing: const Icon(Icons.chevron_right),
        onTap: () async {
          final r = await Navigator.push<List<String>>(
            context,
            MaterialPageRoute(builder: (_) => _PantallaCategorias(api: widget.api, excluidas: exclCat)),
          );
          if (r != null) await _guardar({'excluir_categorias': r});
        },
      ),
      ListTile(
        leading: const Icon(Icons.block),
        title: const Text('Palabras excluidas'),
        subtitle: const Text('Productos cuyo nombre, slug o categoría contenga alguna no se publican'),
      ),
      _Etiquetas(
        valores: exclPal,
        pista: 'Agregar palabra',
        alCambiar: (v) => _guardar({'excluir_productos': v}),
      ),
      ListTile(
        leading: const Icon(Icons.design_services_outlined),
        title: const Text('Servicios excluidos'),
        subtitle: Text(exclServ.isEmpty ? 'Se publican todos' : '${exclServ.length} excluidos'),
        trailing: IconButton(
          icon: const Icon(Icons.add),
          tooltip: 'Excluir un servicio',
          onPressed: () async {
            final slug = await Navigator.push<String>(
              context,
              MaterialPageRoute(builder: (_) => _ElegirServicio(api: widget.api)),
            );
            if (slug != null && !exclServ.contains(slug)) await _guardar({'excluir_servicios': [...exclServ, slug]});
          },
        ),
      ),
      if (exclServ.isNotEmpty)
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16),
          child: Wrap(spacing: 6, runSpacing: 6, children: [
            for (final s in exclServ)
              InputChip(
                label: Text(s),
                onDeleted: () => _guardar({'excluir_servicios': exclServ.where((x) => x != s).toList()}),
              ),
          ]),
        ),
      _titulo('Horario y pausas'),
      ListTile(
        leading: const Icon(Icons.wb_twilight),
        title: const Text('No publicar antes de'),
        trailing: Text(a['no_publicar_antes']?.toString() ?? ''),
        onTap: () => _hora('no_publicar_antes'),
      ),
      ListTile(
        leading: const Icon(Icons.nights_stay_outlined),
        title: const Text('No publicar después de'),
        trailing: Text(a['no_publicar_despues']?.toString() ?? ''),
        onTap: () => _hora('no_publicar_despues'),
      ),
      _Contador(
        titulo: 'Espera aleatoria al empezar (min)',
        valor: (a['jitter_inicio_min'] as num?)?.toInt() ?? 0,
        maximo: 60,
        alCambiar: (v) => _guardar({'jitter_inicio_min': v}),
      ),
      ListTile(
        title: const Text('Pausa entre estados'),
        trailing: Text(_rango(a['pausa_entre_estados'])),
        onTap: () => _editarRango('pausa_entre_estados'),
      ),
      ListTile(
        title: const Text('Pausa entre cuentas'),
        trailing: Text(_rango(a['pausa_entre_cuentas'])),
        onTap: () => _editarRango('pausa_entre_cuentas'),
      ),
      _titulo('Textos de los estados'),
      for (final tipo in ['servicio', 'producto', 'promo'])
        ListTile(
          title: Text(etiquetaTipo(tipo)),
          subtitle: Text((a['textos']?[tipo] ?? '').toString(), maxLines: 3, overflow: TextOverflow.ellipsis),
          trailing: const Icon(Icons.edit),
          onTap: () async {
            final v = await _pedirTexto(
              context,
              'Texto de ${etiquetaTipo(tipo).toLowerCase()}',
              'Datos: {titulo} {descripcion} {precio} {url} {wa}',
              (a['textos']?[tipo] ?? '').toString(),
              lineas: 6,
            );
            if (v != null) {
              await _guardar({
                'textos': {tipo: v}
              });
            }
          },
        ),
      _titulo('Avanzado'),
      ListTile(
        leading: const Icon(Icons.restore),
        title: const Text('Volver a config.toml'),
        subtitle: Text((a['modificados_desde_app'] as List? ?? []).isEmpty
            ? 'No hay cambios hechos desde la app'
            : 'Borra los cambios hechos desde la app: ${(a['modificados_desde_app'] as List).join(', ')}'),
        onTap: () async {
          if (!await confirmar(context, 'Restablecer', '¿Borrar todos los ajustes hechos desde la app?', peligro: true)) {
            return;
          }
          try {
            final r = await widget.api.restablecerAjustes();
            if (mounted) setState(() => _a = r);
          } catch (e) {
            if (context.mounted) avisar(context, e, error: true);
          }
        },
      ),
      ListTile(
        leading: const Icon(Icons.computer),
        title: const Text('Conexión con el PC'),
        subtitle: Text(widget.api.base),
        onTap: () => Navigator.push(
          context,
          MaterialPageRoute(
            builder: (_) => PantallaConexion(actual: widget.api, alConectar: widget.alCambiarConexion),
          ),
        ),
      ),
      ListTile(
        leading: const Icon(Icons.logout),
        title: const Text('Desconectar este celular'),
        onTap: () async {
          if (!await confirmar(context, 'Desconectar', 'Se borran la dirección y la clave guardadas en el celular.')) {
            return;
          }
          await Api.olvidar();
          widget.alCambiarConexion(null);
        },
      ),
    ]);
  }

  String _rango(dynamic r) => r is List && r.length == 2 ? '${r[0]}–${r[1]} s' : '';

  Future<void> _hora(String clave) async {
    final actual = (_a?[clave] ?? '00:00').toString().split(':');
    final t = await showTimePicker(
      context: context,
      initialTime: TimeOfDay(hour: int.tryParse(actual[0]) ?? 0, minute: int.tryParse(actual.last) ?? 0),
    );
    if (t == null) return;
    await _guardar({clave: '${t.hour.toString().padLeft(2, '0')}:${t.minute.toString().padLeft(2, '0')}'});
  }

  Future<void> _editarRango(String clave) async {
    final r = _a?[clave] is List ? List.from(_a![clave]) : [0, 0];
    final v = await _pedirTexto(context, 'Pausa en segundos', 'Mínimo y máximo, ej: 25-70', '${r[0]}-${r[1]}');
    if (v == null) return;
    final m = RegExp(r'^\s*(\d+)\s*[-–, ]\s*(\d+)\s*$').firstMatch(v);
    if (m == null) {
      if (mounted) avisar(context, 'Escribe dos números, ej: 25-70', error: true);
      return;
    }
    await _guardar({
      clave: [int.parse(m.group(1)!), int.parse(m.group(2)!)]
    });
  }
}

Future<String?> _pedirTexto(BuildContext context, String titulo, String pista, String inicial, {int lineas = 1}) {
  final c = TextEditingController(text: inicial);
  return showDialog<String>(
    context: context,
    builder: (d) => AlertDialog(
      title: Text(titulo),
      content: TextField(
        controller: c,
        autofocus: true,
        minLines: lineas,
        maxLines: lineas == 1 ? 1 : 12,
        decoration: InputDecoration(helperText: pista, helperMaxLines: 3, border: const OutlineInputBorder()),
      ),
      actions: [
        TextButton(onPressed: () => Navigator.pop(d), child: const Text('Cancelar')),
        FilledButton(onPressed: () => Navigator.pop(d, c.text), child: const Text('Guardar')),
      ],
    ),
  );
}

class _Contador extends StatelessWidget {
  const _Contador({required this.titulo, required this.valor, required this.alCambiar, this.maximo = 10});

  final String titulo;
  final int valor;
  final int maximo;
  final void Function(int) alCambiar;

  @override
  Widget build(BuildContext context) => ListTile(
        title: Text(titulo),
        trailing: Row(mainAxisSize: MainAxisSize.min, children: [
          IconButton(onPressed: valor > 0 ? () => alCambiar(valor - 1) : null, icon: const Icon(Icons.remove_circle_outline)),
          SizedBox(width: 28, child: Text('$valor', textAlign: TextAlign.center, style: Theme.of(context).textTheme.titleMedium)),
          IconButton(onPressed: valor < maximo ? () => alCambiar(valor + 1) : null, icon: const Icon(Icons.add_circle_outline)),
        ]),
      );
}

class _Etiquetas extends StatelessWidget {
  const _Etiquetas({required this.valores, required this.pista, required this.alCambiar});

  final List<String> valores;
  final String pista;
  final void Function(List<String>) alCambiar;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16),
        child: Wrap(spacing: 6, runSpacing: 6, children: [
          for (final v in valores) InputChip(label: Text(v), onDeleted: () => alCambiar(valores.where((x) => x != v).toList())),
          ActionChip(
            avatar: const Icon(Icons.add, size: 18),
            label: Text(pista),
            onPressed: () async {
              final t = await _pedirTexto(context, pista, 'Ej: medalla', '');
              final limpio = t?.trim().toLowerCase() ?? '';
              if (limpio.isNotEmpty && !valores.contains(limpio)) alCambiar([...valores, limpio]);
            },
          ),
        ]),
      );
}

class _PantallaCategorias extends StatefulWidget {
  const _PantallaCategorias({required this.api, required this.excluidas});

  final Api api;
  final List<String> excluidas;

  @override
  State<_PantallaCategorias> createState() => _PantallaCategoriasState();
}

class _PantallaCategoriasState extends State<_PantallaCategorias> {
  List<Map<String, dynamic>>? _cats;
  Object? _error;
  late final Set<String> _excl = widget.excluidas.map((e) => e.toLowerCase()).toSet();

  @override
  void initState() {
    super.initState();
    _cargar();
  }

  Future<void> _cargar({bool refrescar = false}) async {
    setState(() => _error = null);
    try {
      final c = await widget.api.categorias(refrescar: refrescar);
      if (mounted) setState(() => _cats = [for (final x in c) Map<String, dynamic>.from(x)]);
    } catch (e) {
      if (mounted) setState(() => _error = e);
    }
  }

  @override
  Widget build(BuildContext context) {
    final cats = _cats;
    return Scaffold(
      appBar: AppBar(
        title: const Text('Categorías'),
        actions: [IconButton(onPressed: () => _cargar(refrescar: true), icon: const Icon(Icons.refresh))],
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () => Navigator.pop(context, _excl.toList()..sort()),
        icon: const Icon(Icons.save),
        label: const Text('Guardar'),
      ),
      body: cats == null
          ? (_error != null ? ErrorConReintento(_error!, _cargar) : const Cargando())
          : ListView(padding: const EdgeInsets.only(bottom: 96), children: [
              const Padding(
                padding: EdgeInsets.all(16),
                child: Text('Marca las categorías que SÍ se pueden publicar. Las desmarcadas no salen en los estados.'),
              ),
              for (final c in cats)
                CheckboxListTile(
                  title: Text(c['nombre'].toString()),
                  subtitle: Text('${c['productos']} productos · ${c['slug']}'),
                  value: !_excl.contains(c['slug'].toString().toLowerCase()),
                  onChanged: (v) => setState(() {
                    final s = c['slug'].toString().toLowerCase();
                    if (v == true) {
                      _excl.remove(s);
                    } else {
                      _excl.add(s);
                    }
                  }),
                ),
            ]),
    );
  }
}

class _ElegirServicio extends StatefulWidget {
  const _ElegirServicio({required this.api});

  final Api api;

  @override
  State<_ElegirServicio> createState() => _ElegirServicioState();
}

class _ElegirServicioState extends State<_ElegirServicio> {
  List<Map<String, dynamic>>? _servicios;
  Object? _error;

  @override
  void initState() {
    super.initState();
    _cargar();
  }

  Future<void> _cargar() async {
    try {
      final c = await widget.api.catalogo();
      if (mounted) setState(() => _servicios = [for (final s in (c['servicio'] as List? ?? [])) Map<String, dynamic>.from(s)]);
    } catch (e) {
      if (mounted) setState(() => _error = e);
    }
  }

  @override
  Widget build(BuildContext context) {
    final s = _servicios;
    return Scaffold(
      appBar: AppBar(title: const Text('Excluir un servicio')),
      body: s == null
          ? (_error != null ? ErrorConReintento(_error!, _cargar) : const Cargando())
          : ListView(children: [
              for (final it in s)
                ListTile(
                  leading: const Icon(Icons.design_services_outlined),
                  title: Text(it['titulo'].toString()),
                  subtitle: Text(it['url'].toString()),
                  onTap: () => Navigator.pop(context, it['id'].toString().split(':').last),
                ),
            ]),
    );
  }
}
