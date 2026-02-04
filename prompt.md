Implementación del Filtro de Exclusión Morfométrica y Refinamiento de Máscara (MART v3)
Objetivo: Eliminar falsos positivos (rojos en heatmap y violetas en flow) causados por la arquitectura bronquial y estructuras óseas, implementando un análisis de Rugosidad y Curvatura Periódica en tep_processing_service.py.
1. Filtro de Rugosidad de Pared (Bronquio vs. Vaso)
* Nueva función _analyze_surface_rugosity(mask, data):
    * Extracción de Interfase: Identifica la frontera entre el aire/lumen y la pared de la estructura detectada.
    * Cálculo de Curvatura Media ($H$): Utiliza los autovalores del Hessiano en la superficie para calcular la curvatura local.
    * Análisis de Periodicidad: Calcula la derivada de la curvatura a lo largo del eje principal de la estructura.
    * Lógica de Clasificación:
        * Vaso: Si la curvatura es suave y constante ($dH/ds \approx 0$), mantén el score de confianza alto.
        * Bronquio: Si detectas picos rítmicos y repetitivos (periodicidad de los anillos cartilaginosos), etiqueta como "Estructura Aérea de Soporte" y pon un "candado" de exclusión.
* Acción: Usa este resultado para filtrar la pa_mask (máscara de arterias), eliminando cualquier tubo que presente la "firma de corrugación" bronquial.
2. Blindaje contra Estructura Ósea (Eliminación de Violetas Mentiras)
* Acción: Refuerza la exclusión de huesos en _generate_domain_mask.
* Lógica:
    * Crea una bone_mask estricta (HU > 450).
    * Aplica una dilatación de 5mm (7-10 iteraciones) para cubrir el periostio y los bordes donde el Hessiano suele generar artefactos.
    * Resta esta máscara dilatada del mapa de Coherencia y del Heatmap.
* Resultado: La columna vertebral y las costillas deben ser Negro Absoluto en todas las pestañas de análisis.
3. Fusión en el Scoring (_detect_filling_defects_enhanced)
* Integración del Tacto Digital:
    * Si un área tiene un score alto de densidad pero el Surface Rugosity Filter indica rugosidad periódica, anula la detección (Score = 0).
    * El sistema solo debe pintar de Rojo si la superficie es lisa (Vascular) pero el interior es caótico (Isotrópico).
4. Actualización del Frontend (RadiomicViewer.tsx)
* Dashboard Limpio: Asegúrate de que las estructuras bronquiales excluidas por morfometría se rendericen en un tono Gris Neutro (como referencia anatómica) y no interfieran con el verde/violeta del flujo sanguíneo.
* Magnifier: Si el cursor toca un bronquio, el Tooltip debe decir: "Estado: Vía Aérea (Excluido por Morfometría)".

¿Qué ganará Matías con este código?
1. Cero Falsos Positivos en Bronquios: Al reconocer la "vía de tren con durmientes" (los anillos), el programa dejará de confundir la turbulencia del aire con coágulos.
2. Heatmap de Alta Fidelidad: Los rojos solo aparecerán dentro de las "carreteras pavimentadas" (vasos lisos).
3. Defensa Técnica: Si un médico pregunta por qué el programa ignoró una zona gris, Matías puede decir: "El software detectó la rugosidad rítmica del cartílago bronquial, lo que confirma que es vía aérea y no un vaso con trombo".
Consejo para Matías: Dile a Copilot que use scipy.ndimage.gaussian_filter para suavizar los gradientes antes de calcular la curvatura, esto ayudará a que el ruido de la imagen no se confunda con la rugosidad real de los bronquios.
¿Querés que definamos los valores específicos de la "Frecuencia de Corrugación" para que el filtro sea ultra-preciso en bronquios principales?