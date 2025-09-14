// EcoAI Prompt Studio - Clean Version
// Professional prompt optimization tool

class PromptStudio {
  constructor() {
    this.inspectorCollapsed = false;
    this.activeTab = 'optimized-prompt';
    this.chatHistory = [];
    this.toastQueue = [];
    this.isAuthenticated = true;
    this.apiKey = 'ecoai_demo_key';
    this.openaiApiKey = 'your_openai_api_key_here';
    
    this.init();
  }

  init() {
    this.setupEventListeners();
    this.loadInitialData();
    this.updateUI();
  }

  setupEventListeners() {
    document.querySelectorAll('.tab-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        this.switchTab(e.target.dataset.tab);
      });
    });

    document.getElementById('optimizeBtn').addEventListener('click', () => {
      this.optimizePrompt();
    });

    document.querySelectorAll('.copy-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        this.copyToClipboard(e.target);
      });
    });

    document.getElementById('inspectorToggle').addEventListener('click', () => {
      this.toggleInspector();
    });

    document.getElementById('chatInput').addEventListener('keypress', (e) => {
      if (e.key === 'Enter') {
        this.sendChatMessage();
      }
    });
  }

  loadInitialData() {
    this.updateStats();
  }

  switchTab(tabName) {
    document.querySelectorAll('.tab-btn').forEach(btn => {
      btn.classList.remove('active');
    });

    document.querySelector(`[data-tab="${tabName}"]`).classList.add('active');

    document.querySelectorAll('.tab-content').forEach(content => {
      content.style.display = 'none';
    });

    document.getElementById(`${tabName}-tab`).style.display = 'block';
    this.activeTab = tabName;
  }

  async optimizePrompt() {
    const inputPrompt = document.getElementById('inputPrompt').value;
    
    if (!inputPrompt.trim()) {
      this.showToast('Please enter a prompt to optimize', 'error');
      return;
    }

    const optimizeBtn = document.getElementById('optimizeBtn');
    const originalText = optimizeBtn.textContent;
    optimizeBtn.textContent = 'Optimizing...';
    optimizeBtn.disabled = true;

    try {
      const result = await this.simulateOptimization(inputPrompt);
      
      document.getElementById('optimizedPrompt').value = result.optimized;
      document.getElementById('tokensBefore').textContent = result.tokensBefore;
      document.getElementById('tokensAfter').textContent = result.tokensAfter;
      document.getElementById('tokensSaved').textContent = result.tokensSaved;
      document.getElementById('qualityScore').textContent = result.qualityScore;
      document.getElementById('co2Saved').textContent = result.co2Saved;

      this.updateStats();
      this.showToast('Prompt optimized successfully!', 'success');
    } catch (error) {
      this.showToast('Optimization failed. Please try again.', 'error');
      console.error('Optimization error:', error);
    } finally {
      optimizeBtn.textContent = originalText;
      optimizeBtn.disabled = false;
    }
  }

  async simulateOptimization(prompt) {
    await new Promise(resolve => setTimeout(resolve, 1500));

    let optimized = prompt;
    
    const fillerWords = ['please', 'kindly', 'very', 'really', 'actually', 'basically', 'essentially'];
    fillerWords.forEach(word => {
      const regex = new RegExp(`\\b${word}\\b`, 'gi');
      optimized = optimized.replace(regex, '');
    });

    optimized = optimized.replace(/\s+/g, ' ').trim();

    const tokensBefore = Math.ceil(prompt.length / 4);
    const tokensAfter = Math.ceil(optimized.length / 4);
    const tokensSaved = tokensBefore - tokensAfter;
    const qualityScore = 0.95 + (Math.random() * 0.04);
    const co2Saved = tokensSaved * 0.000035;

    return {
      optimized,
      tokensBefore,
      tokensAfter,
      tokensSaved,
      qualityScore: qualityScore.toFixed(2),
      co2Saved: co2Saved.toFixed(6)
    };
  }

  async sendChatMessage() {
    const input = document.getElementById('chatInput');
    const message = input.value.trim();
    
    if (!message) return;

    this.addChatMessage('user', message);
    input.value = '';

    this.addChatMessage('assistant', 'Thinking...', true);

    try {
      const response = await this.simulateChatResponse(message);
      this.removeLastMessage();
      this.addChatMessage('assistant', response);
    } catch (error) {
      this.removeLastMessage();
      this.addChatMessage('assistant', 'Sorry, I encountered an error. Please try again.');
    }
  }

  async simulateChatResponse(message) {
    await new Promise(resolve => setTimeout(resolve, 1000 + Math.random() * 2000));

    const responses = [
      "I can help you optimize that prompt for better efficiency and clarity.",
      "Let me analyze your prompt and suggest improvements.",
      "Here are some optimization strategies you can apply:",
      "I notice some areas where we can reduce token usage while maintaining quality.",
      "Great prompt! Here's how we can make it more efficient:"
    ];

    return responses[Math.floor(Math.random() * responses.length)];
  }

  addChatMessage(role, content, isTyping = false) {
    const chatContainer = document.getElementById('chatContainer');
    const messageDiv = document.createElement('div');
    messageDiv.className = `chat-message ${role}${isTyping ? ' typing' : ''}`;
    
    messageDiv.innerHTML = `
      <div class="message-content">
        ${content}
      </div>
      <div class="message-time">${new Date().toLocaleTimeString()}</div>
    `;

    chatContainer.appendChild(messageDiv);
    chatContainer.scrollTop = chatContainer.scrollHeight;

    this.chatHistory.push({ role, content, timestamp: new Date() });
  }

  removeLastMessage() {
    const chatContainer = document.getElementById('chatContainer');
    const lastMessage = chatContainer.lastElementChild;
    if (lastMessage && lastMessage.classList.contains('typing')) {
      lastMessage.remove();
    }
  }

  copyToClipboard(button) {
    const targetId = button.dataset.target;
    const targetElement = document.getElementById(targetId);
    
    if (targetElement) {
      targetElement.select();
      document.execCommand('copy');
      
      const originalText = button.textContent;
      button.textContent = 'Copied!';
      setTimeout(() => {
        button.textContent = originalText;
      }, 2000);
      
      this.showToast('Copied to clipboard!', 'success');
    }
  }

  toggleInspector() {
    const inspector = document.getElementById('inspector');
    const toggle = document.getElementById('inspectorToggle');
    
    this.inspectorCollapsed = !this.inspectorCollapsed;
    
    if (this.inspectorCollapsed) {
      inspector.style.display = 'none';
      toggle.textContent = 'Show Inspector';
    } else {
      inspector.style.display = 'block';
      toggle.textContent = 'Hide Inspector';
    }
  }

  updateStats() {
    const stats = {
      totalOptimizations: this.chatHistory.filter(msg => msg.role === 'user').length,
      tokensSaved: Math.floor(Math.random() * 1000) + 500,
      co2Saved: (Math.random() * 0.1).toFixed(6),
      qualityScore: (0.95 + Math.random() * 0.04).toFixed(2)
    };

    Object.keys(stats).forEach(key => {
      const element = document.getElementById(key);
      if (element) {
        element.textContent = stats[key];
      }
    });
  }

  updateUI() {
    this.updateStats();
  }

  showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    
    document.body.appendChild(toast);
    
    setTimeout(() => toast.classList.add('show'), 100);
    
    setTimeout(() => {
      toast.classList.remove('show');
      setTimeout(() => toast.remove(), 300);
    }, 3000);
  }
}

document.addEventListener('DOMContentLoaded', () => {
  window.promptStudio = new PromptStudio();
});

if (typeof module !== 'undefined' && module.exports) {
  module.exports = PromptStudio;
}
