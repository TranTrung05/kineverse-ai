using System;
using System.Collections.Concurrent;
using System.Text;
using UnityEngine;

/// <summary>
/// KineverseBridge: Cầu nối thời gian thực giữa AI Core và Unity Scene (NCKH_UTT).
/// Thực thi theo đặc tả kineverse-interaction/1.0 (INTEGRATION_CONTRACT.md).
/// 
/// Hỗ trợ cả 2 chế độ:
/// 1. Standalone / Editor: Nhận lệnh từ AI Core qua WebSocket (hoặc IPC).
/// 2. WebGL: Nhận lệnh trực tiếp từ JavaScript thông qua SendMessage("KineverseBridge", "OnWebCommand", jsonString).
/// </summary>
public class KineverseBridge : MonoBehaviour
{
    public static KineverseBridge Instance { get; private set; }

    [Header("References")]
    [Tooltip("Gắn PlayerInteractor trên Player vào đây (nếu để trống script sẽ tự tìm).")]
    public PlayerInteractor playerInteractor;
    [Tooltip("Gắn PlayerController trên Player vào đây (nếu để trống script sẽ tự tìm).")]
    public PlayerController playerController;

    [Header("Network Settings (Local Testing)")]
    public int listenPort = 8766;
    public bool autoStartServer = true;

    [Header("Control Sensitivity")]
    public float handMoveSensitivity = 0.05f;
    public float handRotateSensitivity = 2.0f;
    public float handWheelSensitivity = 0.5f;

    // Hàng đợi lệnh từ thread mạng đẩy về Unity Main Thread
    private readonly ConcurrentQueue<InteractionMessage> _commandQueue = new ConcurrentQueue<InteractionMessage>();

    [System.Serializable]
    public class InteractionPayload
    {
        public float dx;
        public float dy;
        public float delta;
        public string hand;
        public string gesture;
        public PositionData position;
    }

    [System.Serializable]
    public class PositionData
    {
        public float x;
        public float y;
        public float z;
    }

    [System.Serializable]
    public class InteractionMessage
    {
        public string type;
        public string message_id;
        public string source;
        public string command;
        public double timestamp;
        public InteractionPayload payload;
    }

    [System.Serializable]
    public class AckMessage
    {
        public string type = "interaction_ack";
        public string message_id;
        public string status = "ok";
        public double timestamp;
        public string error_code;
        public string error;
    }

    void Awake()
    {
        if (Instance == null) Instance = this;
        else Destroy(gameObject);

        if (playerInteractor == null) playerInteractor = FindFirstObjectByType<PlayerInteractor>();
        if (playerController == null) playerController = FindFirstObjectByType<PlayerController>();
    }

    void Start()
    {
        Debug.Log("[KineverseBridge] Khởi tạo cầu nối điều khiển thực hành ảo.");
#if !UNITY_WEBGL || UNITY_EDITOR
        if (autoStartServer)
        {
            StartLocalReceiver();
        }
#endif
    }

    void Update()
    {
        // Xử lý các lệnh AI trên Main Thread của Unity
        while (_commandQueue.TryDequeue(out var msg))
        {
            ExecuteCommand(msg);
        }
    }

    /// <summary>
    /// Điểm vào cho WebGL: Webpage gọi thẳng qua UnityInstance.SendMessage("KineverseBridge", "OnWebCommand", json)
    /// </summary>
    public void OnWebCommand(string jsonMessage)
    {
        try
        {
            var msg = JsonUtility.FromJson<InteractionMessage>(jsonMessage);
            if (msg != null && msg.type == "interaction")
            {
                _commandQueue.Enqueue(msg);
            }
        }
        catch (Exception ex)
        {
            Debug.LogWarning("[KineverseBridge] Lỗi parse JSON WebGL: " + ex.Message);
        }
    }

    /// <summary>
    /// Thực thi lệnh nghiệp vụ của Lab (GRAB, RELEASE, MOVE, ROTATE, SCALE, ...)
    /// </summary>
    private void ExecuteCommand(InteractionMessage msg)
    {
        if (playerInteractor == null) return;

        string cmd = msg.command;
        var p = msg.payload ?? new InteractionPayload();

        switch (cmd)
        {
            case "SELECT":
                // Chọn hoặc bật highlight vật thể đang trỏ vào
                if (playerInteractor.Target != null && HighlightManager.Instance != null)
                {
                    HighlightManager.Instance.Toggle(playerInteractor.Target);
                }
                break;

            case "GRAB":
                // Nắm vật thể đang ngắm tới (tương đương nhấn chuột trái)
                if (playerInteractor.Held == null && playerInteractor.Target != null)
                {
                    playerInteractor.BeginGrab(playerInteractor.Target);
                    Debug.Log($"[KineverseBridge] Đã GRAB vật thể: {playerInteractor.Target.name}");
                }
                break;

            case "RELEASE":
                // Thả vật thể đang cầm
                if (playerInteractor.Held != null)
                {
                    Debug.Log($"[KineverseBridge] Đã RELEASE vật thể: {playerInteractor.Held.name}");
                    playerInteractor.EndGrab();
                }
                break;

            case "MOVE":
                // Điều khiển vị trí vật thể khi đang chụm tay
                if (playerInteractor.Held != null)
                {
                    float dx = p.dx * handMoveSensitivity;
                    float dy = p.dy * handMoveSensitivity;
                    // Tinh chỉnh khoảng cách hoặc độ lệch góc nhìn
                    playerInteractor.holdDistance = Mathf.Clamp(
                        playerInteractor.holdDistance - dy * 0.05f,
                        playerInteractor.minHoldDistance,
                        playerInteractor.maxHoldDistance
                    );
                }
                break;

            case "SCALE":
                // Thay đổi khoảng cách cầm xa / gần
                if (playerInteractor.Held != null)
                {
                    float delta = p.delta * handWheelSensitivity;
                    playerInteractor.holdDistance = Mathf.Clamp(
                        playerInteractor.holdDistance + delta,
                        playerInteractor.minHoldDistance,
                        playerInteractor.maxHoldDistance
                    );
                }
                break;

            case "SWITCH_MODE":
                // Đổi chế độ hoặc hủy highlight
                if (playerInteractor.Target != null && HighlightManager.Instance != null)
                {
                    HighlightManager.Instance.Toggle(playerInteractor.Target);
                }
                break;

            case "CANCEL":
            case "RESET":
                // Hủy cầm nắm khẩn cấp
                if (playerInteractor.Held != null)
                {
                    playerInteractor.EndGrab();
                }
                break;
        }
    }

#if !UNITY_WEBGL || UNITY_EDITOR
    private System.Net.Sockets.TcpListener _tcpListener;
    private System.Threading.Thread _tcpThread;
    private bool _running = false;

    private void StartLocalReceiver()
    {
        try
        {
            _running = true;
            _tcpListener = new System.Net.Sockets.TcpListener(System.Net.IPAddress.Loopback, listenPort);
            _tcpListener.Start();
            _tcpThread = new System.Threading.Thread(ListenForClients) { IsBackground = true };
            _tcpThread.Start();
            Debug.Log($"[KineverseBridge] Local Socket Listener mở tại port {listenPort}");
        }
        catch (Exception e)
        {
            Debug.LogWarning($"[KineverseBridge] Không thể mở socket {listenPort} (Có thể đang dùng WebGL/Mock): {e.Message}");
        }
    }

    private void ListenForClients()
    {
        while (_running)
        {
            try
            {
                var client = _tcpListener.AcceptTcpClient();
                var stream = client.GetStream();
                byte[] buffer = new byte[4096];

                while (_running && client.Connected)
                {
                    int bytesRead = stream.Read(buffer, 0, buffer.Length);
                    if (bytesRead == 0) break;

                    string text = Encoding.UTF8.GetString(buffer, 0, bytesRead);
                    // Đẩy chuỗi vào hàm xử lý
                    OnWebCommand(text);

                    // Trả ACK nếu là interaction
                    string ackJson = "{\"type\":\"interaction_ack\",\"status\":\"ok\"}\n";
                    byte[] ackBytes = Encoding.UTF8.GetBytes(ackJson);
                    stream.Write(ackBytes, 0, ackBytes.Length);
                }
            }
            catch
            {
                // Client ngắt kết nối
            }
        }
    }

    void OnDestroy()
    {
        _running = false;
        try { _tcpListener?.Stop(); } catch { }
        try { _tcpThread?.Abort(); } catch { }
    }
#endif
}
