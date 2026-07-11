const { createApp } = Vue;

createApp({
  data() {
    return {
      // ===== 认证 =====
      token: localStorage.getItem("token") || null,
      currentUser: JSON.parse(localStorage.getItem("currentUser") || "null"),
      authMode: "login",
      authForm: { username: "", password: "" },
      authError: "",
      authLoading: false,

      // ===== 视图 =====
      view: "chat",
      dark: true,

      // ===== 对话 =====
      conversations: [],
      currentConvId: null,

      // ===== 聊天 =====
      draft: "",
      isStreaming: false,
      messages: [],

      // ===== 侧边栏文档 =====
      sidebarDocs: [],

      // ===== 文档管理（完整页） =====
      docs: [],
      docSearch: "",
      docSearchInput: "",
      pageSize: 10,
      page: 1,
      total: 0,
      totalPages: 0,
      dragging: false,
      uploading: false,
      uploadingFiles: [],
    };
  },

  async mounted() {
    document.documentElement.classList.toggle("dark", this.dark);
    if (this.token) {
      try {
        const r = await fetch("/auth/me", { headers: this.apiHeaders() });
        if (r.ok) {
          const data = await r.json();
          this.currentUser = data.user;
          localStorage.setItem("currentUser", JSON.stringify(this.currentUser));
          await this.initAfterLogin();
        } else {
          this.clearAuth();
        }
      } catch (e) {
        this.clearAuth();
      }
    }
  },

  computed: {
    rangeStart() {
      return this.total === 0 ? 0 : (this.page - 1) * this.pageSize + 1;
    },
    rangeEnd() {
      return Math.min(this.page * this.pageSize, this.total);
    },
  },

  methods: {
    // ==================== 认证 ====================
    apiHeaders() {
      return this.token ? { Authorization: "Bearer " + this.token } : {};
    },

    async apiFetch(url, options = {}) {
      const r = await fetch(url, {
        ...options,
        headers: { ...this.apiHeaders(), ...(options.headers || {}) },
      });
      if (r.status === 401) {
        this.clearAuth();
        throw new Error("登录已过期");
      }
      return r;
    },

    clearAuth() {
      this.token = null;
      this.currentUser = null;
      this.conversations = [];
      this.messages = [];
      this.sidebarDocs = [];
      localStorage.removeItem("token");
      localStorage.removeItem("currentUser");
    },

    async auth() {
      if (!this.authForm.username.trim() || !this.authForm.password) {
        this.authError = "请输入用户名和密码";
        return;
      }
      this.authError = "";
      this.authLoading = true;
      try {
        const r = await fetch("/auth/" + this.authMode, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(this.authForm),
        });
        const data = await r.json();
        if (!r.ok) {
          this.authError = data.detail || "操作失败";
          return;
        }
        this.token = data.token;
        this.currentUser = data.user;
        localStorage.setItem("token", this.token);
        localStorage.setItem("currentUser", JSON.stringify(this.currentUser));
        this.authForm = { username: "", password: "" };
        await this.initAfterLogin();
      } catch (e) {
        this.authError = "网络错误：" + e.message;
      } finally {
        this.authLoading = false;
      }
    },

    async initAfterLogin() {
      await this.loadConversations();
      await this.loadSidebarDocs();
      if (this.conversations.length > 0) {
        await this.switchConversation(this.conversations[0].id);
      } else {
        await this.newConversation();
      }
    },

    async logout() {
      if (this.token) {
        try {
          await fetch("/auth/logout", { method: "POST", headers: this.apiHeaders() });
        } catch (e) {}
      }
      this.clearAuth();
    },

    // ==================== 对话管理 ====================
    async loadConversations() {
      try {
        const r = await this.apiFetch("/conversations");
        if (!r.ok) throw new Error("HTTP " + r.status);
        const data = await r.json();
        this.conversations = data.conversations || [];
      } catch (e) {
        console.error("加载对话列表失败:", e);
        this.conversations = [];
      }
    },

    async newConversation() {
      try {
        const r = await this.apiFetch("/conversations", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
        });
        if (!r.ok) throw new Error("HTTP " + r.status);
        const conv = await r.json();
        this.conversations.unshift(conv);
        this.currentConvId = conv.id;
        this.messages = [];
        this.view = "chat";
        this.$nextTick(() => this.$refs.input && this.$refs.input.focus());
      } catch (e) {
        console.error("创建对话失败:", e);
      }
    },

    async switchConversation(convId) {
      if (this.isStreaming) return;
      this.currentConvId = convId;
      this.view = "chat";
      try {
        const r = await this.apiFetch("/conversations/" + convId + "/messages");
        if (!r.ok) throw new Error("HTTP " + r.status);
        const data = await r.json();
        this.messages = (data.messages || []).map((m) => ({
          role: m.role === "assistant" ? "bot" : m.role,
          content: m.content,
          sources: m.sources || [],
        }));
        this.$nextTick(() => this.scrollToBottom());
      } catch (e) {
        console.error("加载消息失败:", e);
        this.messages = [];
      }
    },

    async deleteConv(convId) {
      if (!confirm("确定删除这个对话吗？")) return;
      try {
        const r = await this.apiFetch("/conversations/" + convId, { method: "DELETE" });
        if (!r.ok) throw new Error("HTTP " + r.status);
        this.conversations = this.conversations.filter((c) => c.id !== convId);
        if (this.currentConvId === convId) {
          if (this.conversations.length > 0) {
            await this.switchConversation(this.conversations[0].id);
          } else {
            await this.newConversation();
          }
        }
      } catch (e) {
        alert("删除失败：" + e.message);
      }
    },

    // ==================== 侧边栏文档 ====================
    async loadSidebarDocs() {
      try {
        const r = await this.apiFetch("/documents?page=1&page_size=20");
        if (!r.ok) throw new Error("HTTP " + r.status);
        const data = await r.json();
        this.sidebarDocs = data.documents || [];
      } catch (e) {
        this.sidebarDocs = [];
      }
    },

    switchToDocs() {
      this.view = "docs";
      this.loadDocuments();
    },

    // ==================== 聊天 ====================
    toggleTheme() {
      this.dark = !this.dark;
      document.documentElement.classList.toggle("dark", this.dark);
    },

    scrollToBottom() {
      this.$nextTick(() => {
        const el = this.$refs.messages;
        if (el) el.scrollTop = el.scrollHeight;
      });
    },

    autoGrow(e) {
      const t = e.target;
      t.style.height = "auto";
      t.style.height = Math.min(t.scrollHeight, 140) + "px";
    },

    onKeydown(e) {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        this.send();
      }
    },

    async send() {
      const text = this.draft.trim();
      if (!text || this.isStreaming || !this.currentConvId) return;

      this.messages.push({ role: "user", content: text });
      this.draft = "";
      if (this.$refs.input) this.$refs.input.style.height = "auto";

      this.messages.push({ role: "bot", content: "", streaming: true, sources: [] });
      const bot = this.messages[this.messages.length - 1];
      this.scrollToBottom();

      this.isStreaming = true;
      let finished = false;
      try {
        const resp = await fetch("/chat", {
          method: "POST",
          headers: { ...this.apiHeaders(), "Content-Type": "application/json" },
          body: JSON.stringify({ message: text, conversation_id: this.currentConvId }),
        });

        if (resp.status === 401) {
          this.clearAuth();
          return;
        }
        if (!resp.ok) {
          let msg = "HTTP " + resp.status;
          try { msg = (await resp.json()).detail || msg; } catch (e) {}
          bot.content = "请求失败：" + msg;
          bot.streaming = false;
          this.isStreaming = false;
          return;
        }

        const reader = resp.body.getReader();
        const decoder = new TextDecoder("utf-8");
        let buffer = "";

        while (!finished) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const parts = buffer.split("\n\n");
          buffer = parts.pop();

          for (const part of parts) {
            const line = part.trim();
            if (!line.startsWith("data:")) continue;
            const payload = line.slice(5).trim();
            if (!payload) continue;
            if (payload === "[DONE]") { finished = true; break; }

            let data;
            try { data = JSON.parse(payload); } catch (e) { continue; }

            if (data.error) {
              bot.content += "\n[出错] " + data.error;
            } else if (data.sources) {
              bot.sources = data.sources;
              this.scrollToBottom();
            } else if (data.content) {
              bot.content += data.content;
              this.scrollToBottom();
            }
          }
        }
        if (!bot.content) bot.content = "（未返回内容）";
        // 刷新对话列表（标题可能已更新）
        await this.loadConversations();
      } catch (err) {
        bot.content = "请求失败：" + err.message;
      } finally {
        bot.streaming = false;
        this.isStreaming = false;
        this.$nextTick(() => this.$refs.input && this.$refs.input.focus());
      }
    },

    // ==================== 文档管理（完整页） ====================
    mapDoc(d) {
      return {
        id: d.id,
        name: d.original_filename,
        size: d.file_size != null ? this.formatSize(d.file_size) : "-",
        time: d.created_at || "-",
      };
    },

    async loadDocuments() {
      try {
        const params = new URLSearchParams({ page: String(this.page), page_size: String(this.pageSize) });
        if (this.docSearch) params.set("keyword", this.docSearch);
        const r = await this.apiFetch("/documents?" + params.toString());
        if (!r.ok) throw new Error("HTTP " + r.status);
        const data = await r.json();
        this.docs = (data.documents || []).map((d) => this.mapDoc(d));
        this.total = data.total || 0;
        this.totalPages = data.total_pages || 0;
      } catch (err) {
        console.error("加载文档列表失败:", err);
        this.docs = [];
        this.total = 0;
        this.totalPages = 0;
      }
    },

    onDocSearchInput(e) {
      this.docSearchInput = e.target.value;
      clearTimeout(this._searchTimer);
      this._searchTimer = setTimeout(() => {
        this.docSearch = this.docSearchInput.trim();
        this.page = 1;
        this.loadDocuments();
      }, 300);
    },

    goToPage(p) {
      if (p < 1 || p > this.totalPages || p === this.page) return;
      this.page = p;
      this.loadDocuments();
    },
    prevPage() { this.goToPage(this.page - 1); },
    nextPage() { this.goToPage(this.page + 1); },
    onPageSizeChange() {
      this.page = 1;
      this.loadDocuments();
    },

    triggerUpload() {
      if (this.uploading) return;
      this.$refs.file && this.$refs.file.click();
    },
    onPick(e) {
      this.addFiles(Array.from(e.target.files || []));
      e.target.value = "";
    },
    onDrop(e) {
      this.dragging = false;
      this.addFiles(Array.from(e.dataTransfer.files || []));
    },

    async addFiles(files) {
      const valid = files.filter((f) => /\.(txt|pdf|csv|md)$/i.test(f.name));
      const invalid = files.length - valid.length;
      if (invalid > 0) alert("已忽略 " + invalid + " 个不支持的文件（仅支持 .txt, .pdf, .csv, .md）");
      if (!valid.length) return;

      this.uploading = true;
      try {
        for (const f of valid) {
          this.uploadingFiles.push({ name: f.name, size: this.formatSize(f.size), percent: 0, phase: "uploading" });
          const entry = this.uploadingFiles[this.uploadingFiles.length - 1];
          try {
            const data = await this.uploadOne(f, entry);
            const info = data && data.results && data.results[0];
            if (info && info.deduplicated) {
              alert(`「${f.name}」已上传过，重复入库`);
            }
          } catch (err) {
            alert(`「${f.name}」上传失败：` + err.message);
          } finally {
            this.uploadingFiles = this.uploadingFiles.filter((e) => e !== entry);
          }
        }
        await this.loadDocuments();
        await this.loadSidebarDocs();
      } finally {
        this.uploading = false;
      }
    },

    uploadOne(file, entry) {
      return new Promise((resolve, reject) => {
        const form = new FormData();
        form.append("files", file);

        const xhr = new XMLHttpRequest();
        xhr.open("POST", "/documents/upload");
        xhr.setRequestHeader("Authorization", "Bearer " + this.token);

        xhr.upload.onprogress = (e) => {
          if (e.lengthComputable) {
            entry.percent = Math.round((e.loaded / e.total) * 100);
            if (entry.percent >= 100) entry.phase = "vectorizing";
          }
        };
        xhr.upload.onload = () => {
          entry.percent = 100;
          entry.phase = "vectorizing";
        };
        xhr.onload = () => {
          if (xhr.status >= 200 && xhr.status < 300) {
            let data = null;
            try { data = JSON.parse(xhr.responseText); } catch (e) {}
            resolve(data);
          } else {
            let msg = "HTTP " + xhr.status;
            try { msg = JSON.parse(xhr.responseText).detail || msg; } catch (e) {}
            reject(new Error(msg));
          }
        };
        xhr.onerror = () => reject(new Error("网络错误"));
        xhr.send(form);
      });
    },

    async removeDoc(id) {
      const doc = this.docs.find((d) => d.id === id);
      if (!doc) return;
      if (!confirm(`确定删除文档「${doc.name}」吗？`)) return;
      try {
        const r = await this.apiFetch("/documents/" + encodeURIComponent(doc.id), { method: "DELETE" });
        if (!r.ok) {
          let msg = "HTTP " + r.status;
          try { msg = (await r.json()).detail || msg; } catch (e) {}
          throw new Error(msg);
        }
        if (this.docs.length <= 1 && this.page > 1) this.page -= 1;
        await this.loadDocuments();
        await this.loadSidebarDocs();
      } catch (err) {
        alert("删除失败：" + err.message);
      }
    },

    formatSize(bytes) {
      if (bytes < 1024) return bytes + " B";
      if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
      return (bytes / 1024 / 1024).toFixed(1) + " MB";
    },
  },
}).mount("#app");
