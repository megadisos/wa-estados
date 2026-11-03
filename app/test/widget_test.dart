import 'package:estados_control/api.dart';
import 'package:estados_control/comun.dart';
import 'package:estados_control/pantallas/conexion.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('normaliza la dirección del PC', () {
    expect(Api.normalizar('100.1.2.3'), 'http://100.1.2.3:8770');
    expect(Api.normalizar('http://100.1.2.3:9000/'), 'http://100.1.2.3:9000');
    expect(Api.normalizar(' mi-pc '), 'http://mi-pc:8770');
  });

  test('formatea fechas', () {
    expect(fechaBonita('2026-11-04'), 'miércoles 4 nov');
    expect(fechaHora('2026-11-04T17:05:00-05:00'), '4 nov 5:05 p. m.');
    expect(isoFecha(DateTime(2026, 1, 9)), '2026-01-09');
  });

  testWidgets('la pantalla de conexión pide dirección y clave', (tester) async {
    await tester.pumpWidget(MaterialApp(home: PantallaConexion(alConectar: (_) {})));
    expect(find.text('Dirección del PC'), findsOneWidget);
    expect(find.text('Clave'), findsOneWidget);
    await tester.tap(find.text('Conectar'));
    await tester.pump();
    expect(find.text('Escribe la dirección y la clave'), findsOneWidget);
  });
}
