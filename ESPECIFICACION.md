Aquí tienes el compendio total y definitivo de la "tubería" (pipeline) de MART. Este resumen unifica la física, las matemáticas avanzadas de tensores y la lógica de visualización que hemos pulido. Es el "libro de estrategia" completo de tu motor de detección.

---

# MART: Resumen Integral del Motor de Procesamiento TEP

MART (Medical Analysis & Radiomic Tool) es un sistema de visión computacional de grado clínico que utiliza **biomarcadores radiómicos** y **geometría diferencial** para detectar tromboembolismo pulmonar.

## 1. Fase de Análisis Físico y Densidad

Todo comienza con la interpretación de la materia a través de los rayos X.

* **Normalización HU:** MART calibra la imagen en Unidades Hounsfield. El rango de detección se ha optimizado entre **$15$ y $120$ HU**.
* **$15$ - $30$ HU:** Captura TEP crónico (trombos antiguos y más oscuros).
* **$30$ - $90$ HU:** Captura TEP agudo (fresco).
* **$90$ - $120$ HU:** Captura TEP mixto (parcialmente mezclado con contraste).


* **Acondicionamiento de Señal:** Se aplica un filtro Gaussiano para eliminar el ruido electrónico sin degradar los bordes de los vasos sanguíneos.

## 2. Segmentación Anatómica (El Contenedor)

MART delimita el "campo de juego" para evitar falsos positivos en el resto del cuerpo.

* **Máscara de Dominio:** Aísla el parénquima pulmonar y el mediastino.
* **Árbol Arterial Pulmonar ($pa\_mask$):** Identifica las arterias principales mediante el brillo del contraste ($>150$ HU).
* **Sombra de Oclusión:** Dilata el árbol arterial (8 iteraciones) para incluir zonas donde el coágulo tapa la sangre por completo y el contraste no puede pasar.

## 3. Geometría de Tubos: Tensores de Hessiana

MART utiliza el análisis de **Escala de Espacio (Scale-Space)** para "sentir" la forma de los objetos.

* **Vesselness de Frangi:** Calcula las segundas derivadas de la imagen para hallar autovalores ($\lambda_1, \lambda_2, \lambda_3$).
* **Ajuste Sub-vóxel:** Procesa en escalas de $\sigma = 0.5$ y $1.0$. Esto permite que la matemática detecte arterias de apenas **$1$ o $2$ píxeles** de ancho, algo que el ojo humano suele ignorar por fatiga.

## 4. Geometría de Superficie: Tensores de Ricci

Esta es la capa de "geometría Riemanniana" que diferencia a MART de otros software.

* **Curvatura de Ricci:** En lugar de solo buscar "tubos", MART analiza la deformación de la superficie interna del vaso.
* **Detección de Anomalías:** Un vaso sano tiene una curvatura constante. Un trombo pegado a la pared genera una **anomalía en la variedad geométrica**. El Tensor de Ricci detecta este "relieve" anómalo, permitiendo distinguir un coágulo de una simple irregularidad en la pared arterial.

## 5. Integridad de Red: Análisis Fractal

MART evalúa la salud del sistema como un todo, no solo manchas aisladas.

* **Dimensión Fractal ($Df$):** El sistema vascular pulmonar es un fractal natural. MART mide la complejidad de la ramificación usando algoritmos de *Box-counting*.
* **Pérdida de Complejidad:** Si un pulmón tiene una dimensión fractal significativamente menor que el otro, MART confirma que hay "ramas muertas" debido a una obstrucción proximal, lo que eleva la confianza del hallazgo.

## 6. Dinámica de Fluidos: Coherencia de Flujo (FAC)

MART analiza cómo se mueve la sangre alrededor del sospechoso.

* **Laplaciano de Hodge:** Detecta discontinuidades en el gradiente de contraste.
* **Coherencia de Flujo:** Un trombo causa turbulencia o detención del flujo. Si la coherencia cae bruscamente en una zona de alta densidad, se confirma la presencia de un obstáculo físico (el coágulo).

## 7. El Veredicto: Sistema de Puntuación (Scoring)

MART suma evidencias para decidir si pone un pinche **Rojo (Definite)** o **Amarillo (Suspicious)**:

| Prueba | Evidencia | Puntos |
| --- | --- | --- |
| **Densidad (HU)** | ¿Está en el rango $15-120$? | **+1.0 a +2.0** |
| **Geometría (Hessian/Ricci)** | ¿Tiene forma de vaso deformado? | **+1.0** |
| **Física (FAC/Fractal)** | ¿Interrumpe el flujo o la red? | **+1.0** |

* **Validación Topológica:** Antes de dar el veredicto, MART verifica si la mancha está conectada al árbol arterial. Si está aislada en el aire o en el músculo, se descarta como ruido.

## 8. Visualización de Precisión (Heatmap 1:1)

Para que el médico pueda validar los resultados, MART genera una capa visual perfecta.

* **Pseudocolor LUT:** Crea un mapa de calor donde el **Rojo** representa la densidad exacta del trombo.
* **Mapeo 512x512:** El mapa de color se genera sin recortes en el eje Z y en la resolución original del TAC, asegurando que el Pinche, el Color y el DICOM coincidan píxel por píxel.

---

**Resultado Final:** MART entrega un **Reporte de Auditoría** con el volumen total del coágulo en $cm^3$, el porcentaje de obstrucción de Qanadli y una guía visual interactiva para que el médico tome la decisión final con total seguridad.

¿Te gustaría que preparemos una presentación simplificada de estos puntos para que puedas incluirla en la documentación oficial de "Crescendo"? Sería el complemento perfecto para el lanzamiento.