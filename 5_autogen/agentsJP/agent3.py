from autogen_core import MessageContext, RoutedAgent, message_handler
from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.messages import TextMessage
from autogen_ext.models.openai import OpenAIChatCompletionClient
import messages
import random


class Agent(RoutedAgent):

    # Cambia este mensaje de sistema para reflejar las características únicas de este agente

    system_message = """
    Eres un innovador en el ámbito del fitness y la socialización. Tu tarea es concebir nuevas ideas de negocio que fusionen el deporte con la creación de comunidades, utilizando IA Agentic para optimizar el tiempo de los usuarios y ofrecerles una experiencia única.
    Te interesan proyectos que fomenten el bienestar físico y mental en un ambiente social activo.
    Buscas desarrollar conceptos que integren entrenamiento físico, eventos grupales y plataformas digitales.
    Eres energético, un líder natural y valoras las conexiones humanas. Tienes una mente abierta, pero a veces te puedes obsesionar con los detalles.
    Debes comunicar tus ideas de negocio de manera convincente y entusiasta.
    """

    CHANCES_THAT_I_BOUNCE_IDEA_OFF_ANOTHER = 0.5

    # También puedes cambiar el código para hacer el comportamiento diferente, pero ten cuidado de mantener los métodos iguales, en particular las signaturas del método

    def __init__(self, name) -> None:
        super().__init__(name)
        model_client = OpenAIChatCompletionClient(model="gpt-4o-mini", temperature=0.7)
        self._delegate = AssistantAgent(name, model_client=model_client, system_message=self.system_message)

    @message_handler
    async def handle_message(self, message: messages.Message, ctx: MessageContext) -> messages.Message:
        print(f"{self.id.type}: Recibido mensaje")
        text_message = TextMessage(content=message.content, source="user")
        response = await self._delegate.on_messages([text_message], ctx.cancellation_token)
        idea = response.chat_message.content
        if random.random() < self.CHANCES_THAT_I_BOUNCE_IDEA_OFF_ANOTHER:
            recipient = messages.find_recipient()
            message = f"Aquí está mi idea de negocio. Puede que no sea tu especialidad, pero por favor refínala y hazla mejor. {idea}"
            response = await self.send_message(messages.Message(content=message), recipient)
            idea = response.content
        return messages.Message(content=idea)