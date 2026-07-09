using System;
using System.Collections;
using UnityEngine;

[Serializable]
public class SpriteMotionData
{
    public string version;
    public SpriteMotionSheet sheet;
    public SpriteMotionAnimation animation;
}

[Serializable]
public class SpriteMotionSheet
{
    public string image;
    public int columns;
    public int rows;
    public int frame_width;
    public int frame_height;
    public int padding;
}

[Serializable]
public class SpriteMotionAnimation
{
    public bool loop;
    public int total_duration_ms;
    public SpriteMotionFrame[] frames;
}

[Serializable]
public class SpriteMotionFrame
{
    public int order;
    public int source_frame;
    public int source_time_ms;
    public int duration_ms;
    public float duration_sec;
    public int sheet_x;
    public int sheet_y;
    public string[] tags;
    public float score;
    public bool locked;
}

[RequireComponent(typeof(SpriteRenderer))]
public class VariableFrameSpritePlayer : MonoBehaviour
{
    [SerializeField] private SpriteRenderer targetRenderer;
    [SerializeField] private Sprite[] sprites;
    [SerializeField] private TextAsset timingJson;
    [SerializeField] private float speedMultiplier = 1f;
    [SerializeField] private bool playOnEnable = true;

    private SpriteMotionData data;
    private Coroutine playback;

    private void Awake()
    {
        if (targetRenderer == null)
        {
            targetRenderer = GetComponent<SpriteRenderer>();
        }

        if (timingJson != null)
        {
            data = JsonUtility.FromJson<SpriteMotionData>(timingJson.text);
        }
    }

    private void OnEnable()
    {
        if (playOnEnable)
        {
            Play();
        }
    }

    private void OnDisable()
    {
        Stop();
    }

    public void Play()
    {
        Stop();
        if (data == null || data.animation == null || data.animation.frames == null || sprites == null || sprites.Length == 0)
        {
            return;
        }

        playback = StartCoroutine(PlayRoutine());
    }

    public void Stop()
    {
        if (playback != null)
        {
            StopCoroutine(playback);
            playback = null;
        }
    }

    private IEnumerator PlayRoutine()
    {
        do
        {
            foreach (SpriteMotionFrame frame in data.animation.frames)
            {
                if (frame.order >= 0 && frame.order < sprites.Length)
                {
                    targetRenderer.sprite = sprites[frame.order];
                }

                float duration = Mathf.Max(0.001f, frame.duration_sec / Mathf.Max(0.001f, speedMultiplier));
                yield return new WaitForSeconds(duration);
            }
        } while (data.animation.loop);

        playback = null;
    }
}
