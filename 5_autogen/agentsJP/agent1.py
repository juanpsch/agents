from autogen_core import MessageContext, RoutedAgent, message_handler
from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.messages import TextMessage
from autogen_ext.models.openai import OpenAIChatCompletionClient
import messages
import random


class Agent(RoutedAgent):

    system_message = """
    Eres un innovador en el ámbito del fitness y la socialización. Tu misión es idear nuevos conceptos de negocio que fusionen el deporte con tecnologías que faciliten la interacción social, permitiendo a las personas mantenerse activas y conectar entre sí. 
    Te interesan las ideas que mejoran la experiencia del usuario y que eliminan tareas redundantes, promoviendo un estilo de vida saludable de manera divertida y atractiva.
    Eres dinámico, proactivo y disfrutas explorando nuevas formas de hacer ejercicio en grupo. Tus debilidades: a veces pasas por alto detalles logísticos y te entusiasmas demasiado con conceptos poco realistas.
    Comparte tus ideas de manera clara y animada, incentivando la colaboración.
    """

    CHANCES_THAT_I_BOUNCE_IDEA_OFF_ANOTHER = 0.5

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