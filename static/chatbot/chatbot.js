document.addEventListener('DOMContentLoaded', function () {
    const toggleButton = document.querySelector('.chatbot-popup-button');
    const popup = document.getElementById('chatbot-popup');
    const form = document.getElementById('chat-form');
    const inputBox = document.getElementById('user-input');
    const chatBox = document.getElementById('chat-box');
    const predefinedButtons = document.querySelectorAll('.predefined-question');

    // Show/hide chatbot popup
    toggleButton.addEventListener('click', () => {
        popup.style.display = popup.style.display === 'flex' ? 'none' : 'flex';
    });

    // Send user message and handle response
    form.addEventListener('submit', function (e) {
        e.preventDefault();
        const message = inputBox.value.trim();
        if (message === '') return;

        appendMessage('user', message);
        inputBox.value = '';

        sendMessageToBackend(message);
    });

    // Handle predefined question clicks
    predefinedButtons.forEach(button => {
        button.addEventListener('click', () => {
            const message = button.textContent;
            appendMessage('user', message);
            sendMessageToBackend(message);
        });
    });

    // Append user or bot message to chat box
    function appendMessage(sender, message) {
        const messageDiv = document.createElement('div');
        messageDiv.className = sender === 'user' ? 'user-message' : 'bot-message';
        messageDiv.textContent = message;
        chatBox.appendChild(messageDiv);
        chatBox.scrollTop = chatBox.scrollHeight;
    }

    // Send message to Flask backend and display bot response
    function sendMessageToBackend(message) {
        fetch('/get-response', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: message })
        })
        .then(response => response.json())
        .then(data => {
            appendMessage('bot', data.response);
        })
        .catch(error => {
            console.error('Error:', error);
            appendMessage('bot', 'Sorry, something went wrong. Please try again later.');
        });
    }
});
