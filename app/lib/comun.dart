import 'package:flutter/material.dart';

import 'api.dart';

void avisar(BuildContext context, Object mensaje, {bool error = false}) {
  final m = ScaffoldMessenger.of(context);
  m.hideCurrentSnackBar();
  m.showSnackBar(SnackBar(
    content: Text(mensaje.toString()),
    backgroundColor: error ? Theme.of(context).colorScheme.error : null,
    behavior: SnackBarBehavior.floating,
  ));
}

Future<bool> confirmar(BuildContext context, String titulo, String texto,
    {String si = 'Sí', bool peligro = false}) async {
  final r = await showDialog<bool>(
    context: context,
    builder: (c) => AlertDialog(
      title: Text(titulo),
      content: Text(texto),
      actions: [
        TextButton(onPressed: () => Navigator.pop(c, false), child: const Text('Cancelar')),
        FilledButton(
          style: peligro
              ? FilledButton.styleFrom(backgroundColor: Theme.of(c).colorScheme.error)
              : null,
          onPressed: () => Navigator.pop(c, true),
          child: Text(si),
        ),
      ],
    ),
  );
  return r ?? false;
}

class Miniatura extends StatelessWidget {
  const Miniatura(this.url, {super.key, this.tipo = '', this.tam = 52});

  final String url;
  final String tipo;
  final double tam;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final icono = Container(
      width: tam,
      height: tam,
      color: cs.surfaceContainerHighest,
      child: Icon(
        switch (tipo) {
          'servicio' => Icons.design_services_outlined,
          'promo' => Icons.local_offer_outlined,
          'fijo' => Icons.push_pin_outlined,
          _ => Icons.shopping_bag_outlined,
        },
        color: cs.onSurfaceVariant,
      ),
    );
    final api = Api.actual;
    final delAgente = url.startsWith('/');
    return ClipRRect(
      borderRadius: BorderRadius.circular(8),
      child: url.isEmpty || (delAgente && api == null)
          ? icono
          : Image.network(delAgente ? api!.urlCompleta(url) : url,
              headers: delAgente ? api!.cabeceras : null,
              width: tam,
              height: tam,
              fit: BoxFit.cover,
              errorBuilder: (_, _, _) => icono),
    );
  }
}

String etiquetaTipo(String tipo) => switch (tipo) {
      'servicio' => 'Servicio',
      'producto' => 'Producto',
      'promo' => 'Promo de la semana',
      'fijo' => 'Estado fijo (todos los días)',
      _ => tipo,
    };

const _dias = ['lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo'];
const _meses = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];

/// "2026-11-04" -> "miércoles 4 nov"
String fechaBonita(String? iso) {
  if (iso == null || iso.isEmpty) return '';
  final d = DateTime.tryParse(iso);
  if (d == null) return iso;
  return '${_dias[d.weekday - 1]} ${d.day} ${_meses[d.month - 1]}';
}

/// "2026-11-04T05:03:10-05:00" -> "4 nov 5:03 a. m."
String fechaHora(String? iso) {
  if (iso == null || iso.isEmpty) return '';
  final m = RegExp(r'^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})').firstMatch(iso);
  if (m == null) return iso;
  final h = int.parse(m.group(4)!);
  final h12 = h % 12 == 0 ? 12 : h % 12;
  final ampm = h < 12 ? 'a. m.' : 'p. m.';
  return '${int.parse(m.group(3)!)} ${_meses[int.parse(m.group(2)!) - 1]} $h12:${m.group(5)} $ampm';
}

String isoFecha(DateTime d) =>
    '${d.year.toString().padLeft(4, '0')}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';

class Cargando extends StatelessWidget {
  const Cargando({super.key});

  @override
  Widget build(BuildContext context) => const Center(child: CircularProgressIndicator());
}

class ErrorConReintento extends StatelessWidget {
  const ErrorConReintento(this.error, this.reintentar, {super.key});

  final Object error;
  final VoidCallback reintentar;

  @override
  Widget build(BuildContext context) => Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            Icon(Icons.cloud_off, size: 48, color: Theme.of(context).colorScheme.error),
            const SizedBox(height: 12),
            Text(error.toString(), textAlign: TextAlign.center),
            const SizedBox(height: 12),
            FilledButton.tonal(onPressed: reintentar, child: const Text('Reintentar')),
          ]),
        ),
      );
}
