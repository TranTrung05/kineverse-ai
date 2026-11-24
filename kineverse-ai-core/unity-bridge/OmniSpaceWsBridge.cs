using System;
using System.Collections.Concurrent;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Threading;
using UnityEngine;

public class OmniSpaceWsBridge : MonoBehaviour
{
    public int port = 8766;
    private TcpListener _listener;
    private Thread _thread;
    private volatile bool _running;
    private static readonly ConcurrentQueue<string> Queue = new ConcurrentQueue<string>();

    void Start()
    {
        _running = true;
        _thread = new Thread(ListenLoop) { IsBackground = true };
        _thread.Start();
        Debug.Log($"[OmniSpace] Dang cho AI Core tai cong {port}...");
    }

    void ListenLoop()
    {
        try
        {
            _listener = new TcpListener(IPAddress.Parse("127.0.0.1"), port);
            _listener.Start();
            while (_running)
            {
                if (!_listener.Pending()) { Thread.Sleep(20); continue; }
                var client = _listener.AcceptTcpClient();
                ThreadPool.QueueUserWorkItem(_ => HandleClient(client));
            }
        }
        catch (Exception ex) { if (_running) Queue.Enqueue("ERR:" + ex.Message); }
    }

    void HandleClient(TcpClient client)
    {
        try
        {
            using (client)
            {
                var stream = client.GetStream();
                var buffer = new byte[4096];
                int len = stream.Read(buffer, 0, buffer.Length);
                if (len <= 0) return;
                string req = Encoding.UTF8.GetString(buffer, 0, len);

                if (req.Contains("Sec-WebSocket-Key"))
                {
                    string key = ExtractKey(req);
                    string accept = Convert.ToBase64String(
                        System.Security.Cryptography.SHA1.Create()
                            .ComputeHash(Encoding.UTF8.GetBytes(key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11")));
                    string resp = "HTTP/1.1 101 Switching Protocols\r\n" +
                                  "Upgrade: websocket\r\nConnection: Upgrade\r\n" +
                                  $"Sec-WebSocket-Accept: {accept}\r\n\r\n";
                    byte[] hdr = Encoding.UTF8.GetBytes(resp);
                    stream.Write(hdr, 0, hdr.Length);
                    Queue.Enqueue("CONNECTED");

                    while (_running && client.Connected)
                    {
                        if (!stream.DataAvailable) { Thread.Sleep(10); continue; }
                        int b0 = stream.ReadByte();
                        if (b0 < 0) break;
                        int b1 = stream.ReadByte();
                        if (b1 < 0) break;
                        bool masked = (b1 & 0x80) != 0;
                        long payLen = b1 & 0x7F;
                        if (payLen == 126) payLen = (stream.ReadByte() << 8) | stream.ReadByte();
                        else if (payLen == 127)
                        {
                            payLen = 0;
                            for (int i = 0; i < 8; i++) payLen = (payLen << 8) | (byte)stream.ReadByte();
                        }
                        byte[] mask = new byte[4];
                        if (masked) stream.Read(mask, 0, 4);
                        byte[] data = new byte[payLen];
                        int read = 0;
                        while (read < payLen) read += stream.Read(data, read, (int)payLen - read);
                        if (masked) for (int i = 0; i < data.Length; i++) data[i] ^= mask[i % 4];

                        string msg = Encoding.UTF8.GetString(data);
                        Queue.Enqueue("MSG:" + msg);

                        if (msg.Contains("\"type\":\"connect\"") || msg.Contains("\"type\": \"connect\""))
                            SendWsFrame(stream, "{\"type\":\"connect_ack\",\"protocol\":\"kineverse-interaction/1.0\"}");

                        string msgId = ExtractJsonField(msg, "message_id");
                        if (!string.IsNullOrEmpty(msgId))
                            SendWsFrame(stream, $"{{\"type\":\"interaction_ack\",\"message_id\":\"{msgId}\",\"status\":\"ok\"}}");
                    }
                }
            }
        }
        catch { }
    }

    static void SendWsFrame(NetworkStream stream, string text)
    {
        byte[] payload = Encoding.UTF8.GetBytes(text);
        byte[] frame;
        if (payload.Length < 126)
        {
            frame = new byte[2 + payload.Length];
            frame[0] = 0x81;
            frame[1] = (byte)payload.Length;
            Array.Copy(payload, 0, frame, 2, payload.Length);
        }
        else
        {
            frame = new byte[4 + payload.Length];
            frame[0] = 0x81;
            frame[1] = 126;
            frame[2] = (byte)((payload.Length >> 8) & 0xFF);
            frame[3] = (byte)(payload.Length & 0xFF);
            Array.Copy(payload, 0, frame, 4, payload.Length);
        }
        stream.Write(frame, 0, frame.Length);
    }

    static string ExtractKey(string req)
    {
        foreach (var line in req.Split('\n'))
            if (line.StartsWith("Sec-WebSocket-Key:", StringComparison.OrdinalIgnoreCase))
                return line.Substring(line.IndexOf(':') + 1).Trim();
        return "";
    }

    static string ExtractJsonField(string json, string field)
    {
        string pat = $"\"{field}\"";
        int idx = json.IndexOf(pat, StringComparison.Ordinal);
        if (idx < 0) return "";
        int colon = json.IndexOf(':', idx + pat.Length);
        if (colon < 0) return "";
        int q1 = json.IndexOf('"', colon + 1);
        if (q1 < 0) return "";
        int q2 = json.IndexOf('"', q1 + 1);
        return q2 > q1 ? json.Substring(q1 + 1, q2 - q1 - 1) : "";
    }

    void Update()
    {
        while (Queue.TryDequeue(out string item))
            Debug.Log("[OmniSpace] " + item);
    }

    void OnApplicationQuit()
    {
        _running = false;
        try { _listener?.Stop(); } catch { }
    }
}