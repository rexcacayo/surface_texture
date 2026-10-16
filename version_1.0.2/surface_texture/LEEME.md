# Surface Texture 1.0.2

Complemento para Blender 4.2 a 5.x. Pone **relieve de verdad** (geometría, no color) en cualquier
pieza, listo para imprimir. Todo en modo Objeto; la pieza original no se toca (se oculta).
Licencia GPL-3.0-or-later.

## Qué cambia en 1.0.2

- **Mi imagen** admite también **SVG** (logos vectoriales) y, por defecto, la pone **una sola vez,
  centrada y vista desde arriba** (logos en tapas y placas); «Repetir la imagen» la usa como textura.
  En relieve, lo blanco sube; grabada, lo blanco se hunde. Logo negro sobre fondo blanco: «Invertir».
  (En un SVG siempre cuentan las formas, del color que sean.)
- Si la imagen no se puede leer, avisa claro y no deja ninguna pieza a medias.
- Moleteado más nítido (más detalle por rombo).

## Qué cambia en 1.0.1

- Si vuelves a pulsar «Poner textura» con una pieza que ya tiene textura, ahora **se cambia de
  textura** (se rehace desde la pieza original) en vez de apilar una encima de otra. Para apilar a
  propósito: Ajustes → «Encima de la anterior».

## Uso (Vista 3D → N → pestaña Surface Texture)

1. Selecciona la pieza.
2. Elige la **textura**: moleteado, fibra de carbono, hexágonos, cuero, martillado, madera, piedra,
   ladrillo, estrías o **mi imagen** (PNG/JPG/SVG en grises: blanco alto, negro bajo; se repite).
3. **Profundidad** (0,3–1 mm suele bastar) y **tamaño del dibujo** (lo que mide cada celda).
4. **Grabada** (hacia dentro: la pieza no crece, respeta medidas y encajes) o **en relieve** (hacia fuera).
5. Para los dibujos con forma (moleteado, carbono, hexágonos, ladrillo, estrías, imagen):
   **Cualquier forma** (se proyecta desde los tres ejes, sin costuras) o **Redonda** (envuelve la
   pieza alrededor del eje Z: pomos, mandos, tapones; sin costura).
6. **No tocar la base** (por defecto): lo que apoya en la cama queda liso y plano.
7. **Poner textura** → sale `<pieza>_textura`. Ctrl+Z para probar otra.

Ajustes: solo laterales o solo arriba, y más o menos detalle.

## Cómo funciona

La pieza se rehace con vóxeles finos (según el tamaño del dibujo) para tener detalle uniforme y
siempre cerrado, y cada punto se mueve por su normal según el dibujo. Las texturas de piedra,
martillado, cuero y madera se calculan en el espacio: no tienen costuras en ninguna forma.

## Consejos

- Moleteado para agarre: dibujo de 2–3 mm, profundidad 0,5–0,6 mm, forma Redonda en pomos.
- Con boquilla de 0,4 mm, por debajo de 0,3 mm de profundidad casi no se nota.
- Piezas muy grandes con dibujo muy pequeño pesan mucho: se limita a 1,5 millones de caras y te
  avisa si el detalle se queda corto.
- Los vóxeles redondean un poco las aristas vivas (lo que mide un vóxel).
