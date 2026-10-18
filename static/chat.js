/*  Since the frontend of the project is mostly just updating the html with whatever python
    returns, it would be a lot harder to do the chatbot that way. Since it updates dynamically
    this file is just used to control the chatbot with javascript.
    
    This file runs every time the page reloads or on the onclicks or submits 
 */

// grabs all of the document objects for the chatbot 
const toggle = document.getElementById("chat-toggle")
const panel = document.getElementById("chat-panel")
const closeButton = document.getElementById("chat-close")
const messages = document.getElementById("chat-messages")
const form = document.getElementById("chat-form")
const input = document.getElementById("chat-input")

// the chat history is saved in sessionstorage as a string so we read from that storage 
// using the storage_key and turn it into a js array using json.parse. 
const STORAGE_KEY = "stockwise-chat"; 
let history = JSON.parse(sessionStorage.getItem(STORAGE_KEY) || "[]"); 

// takes the current message history and turns it back into a string using json.stringify and 
// puts it back into sessionstorage using storage_key
function saveHistory(){ 
    const chatHistory = JSON.stringify(history); 
    sessionStorage.setItem(STORAGE_KEY, chatHistory); 
}

// creates a new div plus its class, attaches the text to the div, and then appends it to the 
// messages document object to display on screen
function addBubble(role, text){ 
    const div = document.createElement("div"); 
    div.className = "chat-msg " + role; 
    div.textContent = text; 
    messages.appendChild(div); 
    messages.scrollTop = messages.scrollHeight; 
}

// prints every message in the history with its own bubble 
for (const message of history){
    addBubble(message.role, message.content); 
}

// toggles the chatbot panel whenever the toggle button is clicked 
toggle.addEventListener("click", () => {
   panel.classList.toggle("open")
   if(panel.classList.contains("open")){
    input.focus(); 
   }
})

// hides the panel by deleting the open attribute from the css 
closeButton.addEventListener("click", () => {
    panel.classList.remove("open"); 
})

// runs every time the user submits a message 
form.addEventListener("submit", async (event) => {
    // stops the form from reloading the page, trims the input text, and checks to see if the 
    // input is empty 
    event.preventDefault(); 
    const text = input.value.trim(); 
    if (!text){
        return;
    }
    // otherwise, push the message with the role as the user to history and call addBubble to 
    // display that the message went through on screen 
    history.push({role: "user", content: text}); 
    addBubble("user", text);
    input.value = "";

    // disable the send button while waiting 
    const sendButton = form.querySelector("button"); 
    sendButton.disabled = true; 

    // sends the whole chat history to chat_send() which checks the history, cleans it, and calls
    // get_ai_reply() for a reply from the chatbot. await is used to wait for an answer which is the 
    // response which we then store in data 
    try {
        const response = await fetch("/chat/send", {
            method: "POST", 
            headers: {"Content-Type": "application/json"}, 
            body: JSON.stringify({history: history})
        }); 
        const data = await response.json(); 

        // if the ai replies well, push that message to the chat history and label it as the "assistant"
        // role and add a bubble for it so it shows up on screen 
        if (response.ok) {
            history.push({role: "assistant", content: data.reply}); 
            addBubble("assistant", data.reply); 
            
        }
        else {
            addBubble("error", data.error); 
        }
    } catch (error) {
        addBubble("error", "Could not reach the server, Please Try Again."); 
    }
    // re-enable the send button and save the history 
    sendButton.disabled = false; 
    saveHistory();
});