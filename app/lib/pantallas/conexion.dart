import 'package:flutter/material.dart';

import '../api.dart';
import '../comun.dart';

class PantallaConexion extends StatefulWidget {
  const PantallaConexion({super.key, required this.alConectar, this.actual});

  final void Function(Api) alConectar;
  final Api? actual;

  @override
  State<PantallaConexion> createState() => _PantallaConexionState();
}

class _PantallaConexionState extends State<PantallaConexion> {
  late final _dir = TextEditingController(text: widget.actual?.base ?? '');
  late final _clave = TextEditingController(text: widget.actual?.clave ?? '');
  bool _probando = false;
  bool _ver = false;

  Future<void> _conectar() async {
    final base = Api.normalizar(_dir.text);
    final clave = _clave.text.trim();
    if (base.isEmpty || clave.isEmpty) {
      avisar(context, 'Escribe la dirección y la clave', error: true);
      return;
    }
    setState(() => _probando = true);
    final api = Api(base, clave);
    try {
      await api.ping();
      await api.estado(); // comprueba la clave
      await api.guardar();
      if (!mounted) return;
      widget.alConectar(api);
      if (Navigator.canPop(context)) Navigator.pop(context);
    } on ApiError catch (e) {
      if (mounted) avisar(context, e.codigo == 401 ? 'La clave no es correcta' : e.mensaje, error: true);
    } finally {
      if (mounted) setState(() => _probando = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    return Scaffold(
      appBar: AppBar(title: const Text('Conectar con el PC')),
      body: ListView(
        padding: const EdgeInsets.all(20),
        children: [
          Text('Estados de WhatsApp', style: t.headlineSmall),
          const SizedBox(height: 8),
          const Text(
            'En el PC ejecuta activar_agente.bat: al final muestra la dirección y la clave. '
            'Necesitas Tailscale abierto en el PC y en este celular con la misma cuenta.',
          ),
          const SizedBox(height: 24),
          TextField(
            controller: _dir,
            keyboardType: TextInputType.url,
            autocorrect: false,
            decoration: const InputDecoration(
              labelText: 'Dirección del PC',
              hintText: '100.101.102.103 o http://100.101.102.103:8770',
              border: OutlineInputBorder(),
              prefixIcon: Icon(Icons.computer),
            ),
          ),
          const SizedBox(height: 16),
          TextField(
            controller: _clave,
            obscureText: !_ver,
            autocorrect: false,
            enableSuggestions: false,
            decoration: InputDecoration(
              labelText: 'Clave',
              border: const OutlineInputBorder(),
              prefixIcon: const Icon(Icons.key),
              suffixIcon: IconButton(
                icon: Icon(_ver ? Icons.visibility_off : Icons.visibility),
                onPressed: () => setState(() => _ver = !_ver),
              ),
            ),
          ),
          const SizedBox(height: 24),
          FilledButton.icon(
            onPressed: _probando ? null : _conectar,
            icon: _probando
                ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2))
                : const Icon(Icons.link),
            label: const Text('Conectar'),
          ),
        ],
      ),
    );
  }
}
