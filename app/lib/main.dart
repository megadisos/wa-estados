import 'package:flutter/material.dart';

import 'api.dart';
import 'pantallas/ajustes.dart';
import 'pantallas/conexion.dart';
import 'pantallas/historial.dart';
import 'pantallas/inicio.dart';
import 'pantallas/log.dart';
import 'pantallas/plan.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const EstadosApp());
}

class EstadosApp extends StatefulWidget {
  const EstadosApp({super.key});

  @override
  State<EstadosApp> createState() => _EstadosAppState();
}

class _EstadosAppState extends State<EstadosApp> {
  Api? _api;
  bool _cargando = true;

  @override
  void initState() {
    super.initState();
    Api.cargar().then((a) => setState(() {
          _api = a;
          _cargando = false;
        }));
  }

  void _conectado(Api? api) => setState(() => _api = api);

  @override
  Widget build(BuildContext context) {
    const semilla = Color(0xFF25D366);
    return MaterialApp(
      title: 'Estados WA',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(colorSchemeSeed: semilla, useMaterial3: true),
      darkTheme: ThemeData(colorSchemeSeed: semilla, useMaterial3: true, brightness: Brightness.dark),
      home: _cargando
          ? const Scaffold(body: Center(child: CircularProgressIndicator()))
          : _api == null
              ? PantallaConexion(alConectar: _conectado)
              : Principal(key: ValueKey('${_api!.base}|${_api!.clave}'), api: _api!, alCambiarConexion: _conectado),
    );
  }
}

class Principal extends StatefulWidget {
  const Principal({super.key, required this.api, required this.alCambiarConexion});

  final Api api;
  final void Function(Api?) alCambiarConexion;

  @override
  State<Principal> createState() => _PrincipalState();
}

class _PrincipalState extends State<Principal> {
  int _i = 0;

  @override
  Widget build(BuildContext context) {
    Api.actual = widget.api;
    final paginas = [
      PantallaInicio(api: widget.api, irA: (i) => setState(() => _i = i)),
      PantallaPlan(api: widget.api),
      PantallaHistorial(api: widget.api),
      PantallaLog(api: widget.api, visible: _i == 3),
      PantallaAjustes(api: widget.api, alCambiarConexion: widget.alCambiarConexion),
    ];
    return Scaffold(
      body: IndexedStack(index: _i, children: paginas),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _i,
        onDestinationSelected: (i) => setState(() => _i = i),
        destinations: const [
          NavigationDestination(icon: Icon(Icons.home_outlined), selectedIcon: Icon(Icons.home), label: 'Inicio'),
          NavigationDestination(
              icon: Icon(Icons.event_note_outlined), selectedIcon: Icon(Icons.event_note), label: 'Próxima'),
          NavigationDestination(icon: Icon(Icons.history), label: 'Historial'),
          NavigationDestination(icon: Icon(Icons.terminal), label: 'Log'),
          NavigationDestination(
              icon: Icon(Icons.settings_outlined), selectedIcon: Icon(Icons.settings), label: 'Ajustes'),
        ],
      ),
    );
  }
}
