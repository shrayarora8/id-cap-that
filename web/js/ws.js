// The always-open line. Reconnects on its own, because a phone that locks its
// screen drops the socket and you should not have to reload the page.

let socket = null;
let onMessage = () => {};
let onOpen = () => {};
let onClose = () => {};
let retry = 500;

export function connect(handlers) {
  onMessage = handlers.onMessage || onMessage;
  onOpen = handlers.onOpen || onOpen;
  onClose = handlers.onClose || onClose;
  open();
}

function open() {
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  socket = new WebSocket(`${proto}//${location.host}/ws`);
  socket.binaryType = "arraybuffer";

  socket.onopen = () => {
    retry = 500;
    onOpen();
  };
  socket.onmessage = (ev) => onMessage(JSON.parse(ev.data));
  socket.onclose = () => {
    onClose();
    // Back off, but never wait longer than a few seconds -- on a phone this
    // fires every time the screen locks, and you want it back instantly.
    setTimeout(open, retry);
    retry = Math.min(retry * 2, 4000);
  };
  socket.onerror = () => socket.close();
}

export function sendJSON(obj) {
  if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify(obj));
}

export function sendBinary(buffer) {
  if (socket?.readyState === WebSocket.OPEN) socket.send(buffer);
}

export function isOpen() {
  return socket?.readyState === WebSocket.OPEN;
}
