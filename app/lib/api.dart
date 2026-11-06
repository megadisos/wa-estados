import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

class ApiError implements Exception {
  ApiError(this.mensaje, [this.codigo = 0]);
  final String mensaje;
  final int codigo;

  @override
  String toString() => mensaje;
}

/// Cliente de la API del agente que corre en el PC (agente.py).
class Api {
  Api(this.base, this.clave);

  final String base;
  final String clave;

  /// La conexión en uso (para cargar imágenes que sirve el agente, como las de los estados fijos).
  static Api? actual;

  /// Para una ruta del agente ("/api/fijo?id=...") devuelve la URL completa; una URL normal queda igual.
  String urlCompleta(String url) => url.startsWith('/') ? '$base$url' : url;

  Map<String, String> get cabeceras => {'Authorization': 'Bearer $clave'};

  static const _kBase = 'base';
  static const _kClave = 'clave';

  static Future<Api?> cargar() async {
    final p = await SharedPreferences.getInstance();
    final base = p.getString(_kBase);
    final clave = p.getString(_kClave);
    if (base == null || base.isEmpty || clave == null || clave.isEmpty) return null;
    return Api(base, clave);
  }

  static String normalizar(String direccion) {
    var d = direccion.trim();
    if (d.isEmpty) return d;
    if (!d.startsWith('http://') && !d.startsWith('https://')) d = 'http://$d';
    final uri = Uri.parse(d);
    if (!uri.hasPort) d = '${uri.scheme}://${uri.host}:8770';
    return d.replaceAll(RegExp(r'/+$'), '');
  }

  Future<void> guardar() async {
    final p = await SharedPreferences.getInstance();
    await p.setString(_kBase, base);
    await p.setString(_kClave, clave);
  }

  static Future<void> olvidar() async {
    final p = await SharedPreferences.getInstance();
    await p.remove(_kBase);
    await p.remove(_kClave);
  }

  Future<dynamic> _llamar(String metodo, String ruta,
      {Map<String, String>? query, Object? cuerpo, Duration? espera}) async {
    final uri = Uri.parse('$base$ruta').replace(queryParameters: query);
    final cab = {
      'Authorization': 'Bearer $clave',
      'Content-Type': 'application/json',
    };
    final t = espera ?? const Duration(seconds: 20);
    http.Response r;
    try {
      final c = cuerpo == null ? null : jsonEncode(cuerpo);
      switch (metodo) {
        case 'POST':
          r = await http.post(uri, headers: cab, body: c ?? '{}').timeout(t);
          break;
        case 'PUT':
          r = await http.put(uri, headers: cab, body: c ?? '{}').timeout(t);
          break;
        default:
          r = await http.get(uri, headers: cab).timeout(t);
      }
    } catch (e) {
      throw ApiError(
          'No se pudo conectar con el PC. Revisa que esté encendido, con Tailscale activo en ambos y el agente corriendo.');
    }
    dynamic datos;
    try {
      datos = jsonDecode(utf8.decode(r.bodyBytes));
    } catch (_) {
      datos = null;
    }
    if (r.statusCode >= 400) {
      final msg = datos is Map && datos['error'] != null
          ? datos['error'].toString()
          : 'Error ${r.statusCode}';
      throw ApiError(msg, r.statusCode);
    }
    return datos;
  }

  Future<Map<String, dynamic>> ping() async =>
      Map<String, dynamic>.from(await _llamar('GET', '/api/ping', espera: const Duration(seconds: 8)));

  Future<Map<String, dynamic>> estado() async =>
      Map<String, dynamic>.from(await _llamar('GET', '/api/estado'));

  Future<Map<String, dynamic>> ejecutar(
          {required bool real, String? cuenta, bool ignorarHorario = false, bool sinEspera = false}) async =>
      Map<String, dynamic>.from(await _llamar('POST', '/api/ejecutar', cuerpo: {
        'real': real,
        'cuenta': cuenta,
        'ignorar_horario': ignorarHorario,
        'sin_espera': sinEspera,
      }));

  Future<Map<String, dynamic>> detener({bool forzar = false}) async =>
      Map<String, dynamic>.from(await _llamar('POST', '/api/detener', cuerpo: {'forzar': forzar}));

  Future<Map<String, dynamic>> pausar(bool pausado, {String? hasta}) async =>
      Map<String, dynamic>.from(
          await _llamar('POST', '/api/pausa', cuerpo: {'pausado': pausado, 'hasta': hasta}));

  Future<Map<String, dynamic>> plan({String? fecha}) async => Map<String, dynamic>.from(
      await _llamar('GET', '/api/plan', query: fecha == null ? null : {'fecha': fecha}));

  Future<Map<String, dynamic>> crearPlan(String fecha) async => Map<String, dynamic>.from(
      await _llamar('POST', '/api/plan', cuerpo: {'fecha': fecha}, espera: const Duration(seconds: 90)));

  Future<Map<String, dynamic>> cambiarPlan(String fecha, List<String> ids) async =>
      Map<String, dynamic>.from(await _llamar('PUT', '/api/plan',
          cuerpo: {'fecha': fecha, 'ids': ids}, espera: const Duration(seconds: 90)));

  Future<void> resolverIncierto(String fecha, String cuenta, String id, String accion) async =>
      _llamar('POST', '/api/incierto',
          cuerpo: {'fecha': fecha, 'cuenta': cuenta, 'id': id, 'accion': accion});

  Future<Map<String, dynamic>> catalogo({bool refrescar = false}) async =>
      Map<String, dynamic>.from(await _llamar('GET', '/api/catalogo',
          query: refrescar ? {'refrescar': '1'} : null, espera: const Duration(seconds: 90)));

  Future<List<dynamic>> categorias({bool refrescar = false}) async =>
      List<dynamic>.from(await _llamar('GET', '/api/categorias',
          query: refrescar ? {'refrescar': '1'} : null, espera: const Duration(seconds: 90)));

  Future<Map<String, dynamic>> promo() async => Map<String, dynamic>.from(
      await _llamar('GET', '/api/promo', espera: const Duration(seconds: 90)));

  Future<List<dynamic>> historial({int dias = 30, String? cuenta}) async =>
      List<dynamic>.from(await _llamar('GET', '/api/historial', query: {
        'dias': '$dias',
        'cuenta': ?cuenta,
      }));

  Future<Map<String, dynamic>> log({String archivo = 'estados', int desde = -1}) async =>
      Map<String, dynamic>.from(
          await _llamar('GET', '/api/log', query: {'archivo': archivo, 'desde': '$desde'}));

  Future<Map<String, dynamic>> ajustes() async =>
      Map<String, dynamic>.from(await _llamar('GET', '/api/ajustes'));

  Future<Map<String, dynamic>> guardarAjustes(Map<String, dynamic> cambios) async =>
      Map<String, dynamic>.from(await _llamar('PUT', '/api/ajustes', cuerpo: {'cambios': cambios}));

  Future<Map<String, dynamic>> restablecerAjustes() async =>
      Map<String, dynamic>.from(await _llamar('PUT', '/api/ajustes', cuerpo: {'restablecer': true}));
}
