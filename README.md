## Domina la Ingeniería de IA Agente: Construye Agentes Autónomos de IA

### Un viaje de 6 semanas para programar y desplegar Agentes de IA con OpenAI Agents SDK, CrewAI, LangGraph, AutoGen y MCP

![Agente Autónomo](assets/autonomy.png)

*Si estás viendo esto en Cursor, haz clic derecho sobre el nombre del archivo en el Explorador a la izquierda y selecciona "Abrir vista previa" para ver la versión con formato.*

¡No puedo estar más emocionado de darte la bienvenida! Este es el comienzo de tu aventura de 6 semanas en el poderoso, asombroso y, a menudo, surrealista mundo de la IA Agente.

### Antes de comenzar

¡Estoy aquí para ayudarte a tener el mayor éxito posible! No dudes en ponerte en contacto si podemos ayudarte a través de la plataforma. Siempre es genial conectar con personas en LinkedIn para construir la comunidad. Puedes encontrarme aquí:
[https://www.linkedin.com/in/juan-gabriel-gomila-salas/](https://www.linkedin.com/in/juan-gabriel-gomila-salas/)
También puedes encontrarme en X/Twitter en [@joan_by](https://x.com/joan_by) – si estás en X, ¡no dudes en contactar y seguirnos mútuamente! 😂

### Las no tan temidas instrucciones de configuración

Tal vez sea la última vez que lo diga, pero realmente espero haber creado un entorno que no sea demasiado aterrador de configurar.

* Usuarios de Windows, sus instrucciones están [aquí](setup/SETUP-PC.md)
* Usuarios de Mac, las suyas están [aquí](setup/SETUP-mac.md)
* Usuarios de Linux, las suyas están [aquí](setup/SETUP-linux.md)

Si tienes algún problema, por favor, contacta con nosotros.

### Notas importantes para la semana de CrewAI (Semana 3)

Usuarios de Windows PC: necesitarás haber marcado "gotcha #4" en la parte superior de las [instrucciones SETUP-PC](setup/SETUP-PC.md) — instalando Microsoft Build Tools.
Luego, necesitarás ejecutar este comando en una Terminal de Cursor en el directorio raíz del proyecto para ejecutar los comandos de Crew:
`uv tool install crewai`
Y en caso de que hayas usado Crew antes, podría ser útil hacer esto para asegurarte de tener la última versión:
`uv tool upgrade crewai`

Luego, ten en cuenta lo siguiente para Crew:

1. Hay dos formas en las que puedes trabajar en el proyecto de CrewAI en la semana 3. Puedes revisar el código de cada proyecto mientras lo construyo y luego hacer `crewai run` para verlo en acción. O si prefieres ser más práctico, puedes crear tu propio proyecto Crew desde cero para imitar el mío; por ejemplo, crea `my_debate` junto con `debate` y escribe el código conmigo. ¡Cualquiera de las dos opciones funciona!
2. Usuarios de Windows: hay un nuevo problema que se introdujo recientemente por una de las bibliotecas de Crew. Hasta que esto se solucione, podrías obtener un error de "unicode" cuando intentes ejecutar `crewai create crew`. Si eso sucede, por favor intenta ejecutar este comando en la Terminal primero: `$env:PYTHONUTF8 = "1"`

### Recursos súper útiles

* Los [recursos](https://cursos.frogamesformacion.com/pages/blog/ingenieria-de-agentes-de-ia) del curso con videos
* Muchas guías esenciales en la sección [guides](guides/01_intro.ipynb)
* El cuaderno de [solución de problemas](setup/troubleshooting.ipynb)

### Costos de la API - ¡por favor léeme!

Este curso implica hacer llamadas a OpenAI y otros modelos de frontier, lo que requiere una clave de API y un pequeño gasto, que configuramos en las instrucciones SETUP. Si prefieres no gastar en llamadas a API, hay alternativas más baratas como DeepSeek y alternativas gratuitas como usar Ollama.

Los detalles están [aquí](guides/09_ai_apis_and_ollama.ipynb).

Asegúrate de monitorear tus costos de API para asegurarte de estar completamente feliz con cualquier gasto. Para OpenAI, el panel de control está [aquí](https://platform.openai.com/usage).

### SOBRE TODO -

¡Asegúrate de divertirte con el curso! No podrías haber elegido un mejor momento para aprender sobre IA Agente. ¡Espero que disfrutes cada minuto! Y si te atascas en algún punto, [contáctame](https://www.linkedin.com/in/juan-gabriel-gomila-salas/).
