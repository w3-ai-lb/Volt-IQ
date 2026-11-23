import 'dart:io';
import 'package:flutter/material.dart';
import 'package:camera/camera.dart';
import 'package:google_mlkit_text_recognition/google_mlkit_text_recognition.dart';
import 'package:image_picker/image_picker.dart';
import 'customer_page.dart';
import 'reading_invoice_page.dart';
import '../services/api_service.dart';

class OcrReadingPage extends StatefulWidget {
  final Customer customer;

  const OcrReadingPage({super.key, required this.customer});

  @override
  State<OcrReadingPage> createState() => _OcrReadingPageState();
}

class _OcrReadingPageState extends State<OcrReadingPage> {
  CameraController? _cameraController;
  List<CameraDescription> _cameras = [];
  bool _isCameraInitialized = false;
  File? _imageFile;
  bool _isProcessing = false;
  String _rawExtractedText = '';
  final _readingController = TextEditingController();
  double _previousReading = 0.0;
  List<String> _candidateNumbers = [];

  final _picker = ImagePicker();
  final _textRecognizer = TextRecognizer(script: TextRecognitionScript.latin);

  @override
  void initState() {
    super.initState();
    _initializeCamera();
    _fetchPreviousReading();
  }

  Future<void> _fetchPreviousReading() async {
    final latest = await ApiService.instance.getLatestReadingForCustomer(widget.customer.id);
    if (latest != null && mounted) {
      final prev = latest['current_reading'] ?? latest['reading_value'] ?? 0.0;
      setState(() {
        _previousReading = prev is num ? prev.toDouble() : double.tryParse(prev.toString()) ?? 0.0;
      });
    }
  }

  Future<void> _initializeCamera() async {
    try {
      _cameras = await availableCameras();
      if (_cameras.isNotEmpty) {
        // Use back camera as default
        final backCamera = _cameras.firstWhere(
          (camera) => camera.lensDirection == CameraLensDirection.back,
          orElse: () => _cameras.first,
        );

        _cameraController = CameraController(
          backCamera,
          ResolutionPreset.high,
          enableAudio: false,
        );

        await _cameraController!.initialize();
        if (mounted) {
          setState(() {
            _isCameraInitialized = true;
          });
        }
      }
    } catch (e) {
      debugPrint('Camera Initialization Failed: $e');
    }
  }

  @override
  void dispose() {
    _cameraController?.dispose();
    _readingController.dispose();
    _textRecognizer.close();
    super.dispose();
  }

  // Snaps picture from live camera feed
  Future<void> _capturePhoto() async {
    if (_cameraController == null || !_cameraController!.value.isInitialized) return;

    setState(() {
      _isProcessing = true;
    });

    try {
      final XFile photo = await _cameraController!.takePicture();
      setState(() {
        _imageFile = File(photo.path);
      });
      await _processImage(photo.path);
    } catch (e) {
      setState(() {
        _isProcessing = false;
      });
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Failed to capture image: $e'),
          backgroundColor: Colors.redAccent,
        ),
      );
    }
  }

  // Gallery fallback
  Future<void> _pickFromGallery() async {
    try {
      final pickedFile = await _picker.pickImage(
        source: ImageSource.gallery,
        maxWidth: 1200,
        maxHeight: 1200,
      );

      if (pickedFile == null) return;

      setState(() {
        _imageFile = File(pickedFile.path);
        _isProcessing = true;
        _rawExtractedText = '';
        _readingController.clear();
      });

      await _processImage(pickedFile.path);
    } catch (e) {
      setState(() {
        _isProcessing = false;
      });
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Failed to load gallery image: $e'),
          backgroundColor: Colors.redAccent,
        ),
      );
    }
  }

  // Processes image with ML Kit Text Recognizer
  Future<void> _processImage(String path) async {
    try {
      final inputImage = InputImage.fromFilePath(path);
      final recognizedText = await _textRecognizer.processImage(inputImage);

      String rawText = '';
      for (TextBlock block in recognizedText.blocks) {
        for (TextLine line in block.lines) {
          rawText += '${line.text}\n';
        }
      }

      // Parse text to find all valid candidate numbers (including leading/trailing zeros, decimals)
      final RegExp digitRegExp = RegExp(r'\b\d+(?:\.\d+)?\b');
      final matches = digitRegExp.allMatches(rawText);

      final Set<String> candidates = {};
      for (final match in matches) {
        final val = match.group(0);
        if (val != null && val.trim().isNotEmpty && val.length >= 2) {
          candidates.add(val.trim());
        }
      }

      String parsedValue = '';
      if (candidates.isNotEmpty) {
        // Prefer longer matches first
        final sorted = candidates.toList()..sort((a, b) => b.length.compareTo(a.length));
        parsedValue = sorted.first;
      }

      setState(() {
        _rawExtractedText = rawText;
        _candidateNumbers = candidates.toList();
        if (parsedValue.isNotEmpty) {
          _readingController.text = parsedValue;
        }
        _isProcessing = false;
      });
    } catch (e) {
      setState(() {
        _isProcessing = false;
      });
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('OCR Notice: $e. Please enter reading manually.'),
            backgroundColor: Colors.redAccent,
          ),
        );
      }
    }
  }

  // Reset to live camera scan
  void _retakePhoto() {
    setState(() {
      _imageFile = null;
      _rawExtractedText = '';
      _candidateNumbers = [];
      _readingController.clear();
    });
  }

  Future<void> _submitReading() async {
    final reading = _readingController.text.trim();
    if (reading.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Please enter or scan a valid meter reading'),
          backgroundColor: Colors.redAccent,
        ),
      );
      return;
    }

    final numVal = double.tryParse(reading.replaceAll(RegExp(r'[^0-9.]'), '')) ?? 0.0;

    // Logic: Past meter reading cannot be higher than the new meter reading
    if (_previousReading > 0 && numVal < _previousReading) {
      showDialog(
        context: context,
        builder: (ctx) => AlertDialog(
          backgroundColor: const Color(0xFF1E293B),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
          title: const Row(
            children: [
              Icon(Icons.warning_amber_rounded, color: Colors.amber, size: 28),
              SizedBox(width: 8),
              Text('Meter Reading Alert', style: TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.bold)),
            ],
          ),
          content: Text(
            'The entered reading (${numVal.toStringAsFixed(1)} kWh) is lower than the previous recorded reading (${_previousReading.toStringAsFixed(1)} kWh).\n\nA meter reading cannot decrease over time. Please verify the numbers on the meter.',
            style: const TextStyle(color: Colors.white70, fontSize: 14),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(ctx),
              child: const Text('Correct Number', style: TextStyle(color: Color(0xFF818CF8), fontWeight: FontWeight.bold)),
            ),
          ],
        ),
      );
      return;
    }

    // Calculate consumption and charges
    final consumption = (_previousReading > 0 && numVal >= _previousReading)
        ? (numVal - _previousReading)
        : (numVal > 100 ? (numVal % 250) + 15 : (numVal > 0 ? numVal : 45.0));
    final cost = (consumption * 0.15) + 5.0;

    // Send to the VoltIQ server, which checks the reading and issues the invoice
    await ApiService.instance.recordMeterReading(
      subscriberId: widget.customer.id,
      customerName: widget.customer.name,
      meterNumber: widget.customer.meterNumber,
      previousReading: _previousReading,
      readingValue: reading,
      consumption: consumption,
      cost: cost,
    );

    // Update customer status to Completed
    widget.customer.status = 'Completed';

    Navigator.pushReplacement(
      context,
      MaterialPageRoute(
        builder: (context) => ReadingInvoicePage(
          customer: widget.customer,
          currentReadingStr: reading,
          previousReadingVal: _previousReading,
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF0F172A),
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        elevation: 0,
        title: const Text(
          'Live Meter Scanner',
          style: TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.bold),
        ),
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_ios_new_rounded, color: Colors.white),
          onPressed: () => Navigator.pop(context),
        ),
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 10),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Customer Context Card
            Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: const Color(0xFF1E293B).withOpacity(0.6),
                borderRadius: BorderRadius.circular(20),
                border: Border.all(color: Colors.white.withOpacity(0.08)),
              ),
              child: Row(
                children: [
                  const Icon(Icons.electric_meter_rounded, color: Color(0xFF818CF8), size: 28),
                  const SizedBox(width: 16),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          widget.customer.name,
                          style: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold, fontSize: 15),
                        ),
                        const SizedBox(height: 2),
                        Row(
                          children: [
                            Text(
                              'Meter: ${widget.customer.meterNumber}',
                              style: TextStyle(color: Colors.white.withOpacity(0.4), fontSize: 12),
                            ),
                            const SizedBox(width: 8),
                            Container(
                              padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                              decoration: BoxDecoration(
                                color: Colors.cyan.withOpacity(0.12),
                                borderRadius: BorderRadius.circular(6),
                              ),
                              child: Text(
                                _previousReading > 0 ? 'Prev: ${_previousReading.toStringAsFixed(0)} kWh' : 'Prev: 0 kWh',
                                style: const TextStyle(color: Colors.cyanAccent, fontSize: 11, fontWeight: FontWeight.bold),
                              ),
                            ),
                          ],
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 24),

            // Live Camera View / Static Image Container
            Center(
              child: Container(
                width: double.infinity,
                height: 280,
                decoration: BoxDecoration(
                  color: const Color(0xFF1E293B).withOpacity(0.4),
                  borderRadius: BorderRadius.circular(24),
                  border: Border.all(
                    color: const Color(0xFF4F46E5).withOpacity(0.2),
                    width: 1.5,
                  ),
                ),
                child: ClipRRect(
                  borderRadius: BorderRadius.circular(24),
                  child: Stack(
                    fit: StackFit.expand,
                    children: [
                      // View Decision: Live feed OR captured static image
                      if (_imageFile != null) ...[
                        Image.file(_imageFile!, fit: BoxFit.cover),
                      ] else if (_isCameraInitialized && _cameraController != null) ...[
                        CameraPreview(_cameraController!),
                      ] else ...[
                        const Center(
                          child: CircularProgressIndicator(color: Color(0xFF818CF8)),
                        ),
                      ],

                      // Visual camera target box overlay (Only shown live while taking the photo)
                      if (_imageFile == null)
                        Center(
                          child: Container(
                            width: 280,
                            height: 90,
                            decoration: BoxDecoration(
                              border: Border.all(
                                color: const Color(0xFF818CF8),
                                width: 2,
                              ),
                              borderRadius: BorderRadius.circular(16),
                              color: Colors.black12,
                            ),
                            child: Center(
                              child: Column(
                                mainAxisAlignment: MainAxisAlignment.center,
                                children: [
                                  Icon(
                                    Icons.crop_free_rounded,
                                    color: const Color(0xFF818CF8).withOpacity(0.8),
                                    size: 20,
                                  ),
                                  const SizedBox(height: 4),
                                  Text(
                                    'ALIGN METER DIGITS IN THIS BOX',
                                    style: TextStyle(
                                      color: Colors.white.withOpacity(0.7),
                                      fontSize: 9,
                                      fontWeight: FontWeight.bold,
                                      letterSpacing: 1.0,
                                    ),
                                  ),
                                ],
                              ),
                            ),
                          ),
                        ),

                      if (_isProcessing)
                        Container(
                          color: Colors.black54,
                          child: const Center(
                            child: CircularProgressIndicator(color: Color(0xFF818CF8)),
                          ),
                        ),
                    ],
                  ),
                ),
              ),
            ),
            const SizedBox(height: 16),

            // Live Camera Control Buttons (Only visible before capture)
            if (_imageFile == null)
              Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  IconButton(
                    onPressed: _pickFromGallery,
                    icon: const Icon(Icons.photo_library_rounded, color: Color(0xFF818CF8), size: 28),
                    tooltip: 'Choose from Gallery',
                  ),
                  const SizedBox(width: 24),
                  ElevatedButton.icon(
                    style: ElevatedButton.styleFrom(
                      backgroundColor: const Color(0xFF4F46E5),
                      foregroundColor: Colors.white,
                      padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
                    ),
                    onPressed: _isCameraInitialized ? _capturePhoto : null,
                    icon: const Icon(Icons.camera_alt_rounded),
                    label: const Text('Capture Meter', style: TextStyle(fontWeight: FontWeight.bold)),
                  ),
                ],
              )
            else
              Center(
                child: TextButton.icon(
                  onPressed: _retakePhoto,
                  icon: const Icon(Icons.refresh_rounded, color: Colors.amber),
                  label: const Text('Retake Live Capture', style: TextStyle(color: Colors.amber, fontWeight: FontWeight.bold)),
                ),
              ),

            const SizedBox(height: 24),

            // Extracted Number Textbox (User can edit this)
            const Text(
              'Verified Meter Value (kWh)',
              style: TextStyle(color: Colors.white70, fontSize: 14, fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 10),
            Container(
              decoration: BoxDecoration(
                color: const Color(0xFF1E293B).withOpacity(0.8),
                borderRadius: BorderRadius.circular(16),
                border: Border.all(color: Colors.white.withOpacity(0.1)),
              ),
              child: TextField(
                controller: _readingController,
                keyboardType: TextInputType.number,
                style: const TextStyle(color: Colors.white, fontSize: 20, fontWeight: FontWeight.bold, letterSpacing: 1.5),
                decoration: InputDecoration(
                  hintText: '--- ---',
                  hintStyle: TextStyle(color: Colors.white.withOpacity(0.2)),
                  prefixIcon: const Icon(Icons.pin, color: Colors.white38),
                  border: InputBorder.none,
                  contentPadding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
                ),
              ),
            ),
            if (_candidateNumbers.isNotEmpty) ...[
              const SizedBox(height: 10),
              Text(
                'Detected Values (Tap to select):',
                style: TextStyle(color: Colors.white.withOpacity(0.6), fontSize: 12, fontWeight: FontWeight.w600),
              ),
              const SizedBox(height: 6),
              Wrap(
                spacing: 8,
                runSpacing: 6,
                children: _candidateNumbers.map((numStr) {
                  final isSelected = _readingController.text.trim() == numStr.trim();
                  return ActionChip(
                    backgroundColor: isSelected ? const Color(0xFF4F46E5) : const Color(0xFF1E293B),
                    side: BorderSide(
                      color: isSelected ? const Color(0xFF818CF8) : Colors.white24,
                    ),
                    label: Text(
                      numStr,
                      style: TextStyle(
                        color: isSelected ? Colors.white : Colors.cyanAccent,
                        fontWeight: FontWeight.bold,
                        fontSize: 13,
                      ),
                    ),
                    onPressed: () {
                      setState(() {
                        _readingController.text = numStr;
                      });
                    },
                  );
                }).toList(),
              ),
            ],
            const SizedBox(height: 16),

            // Raw OCR Output Logs (Collapsible helper)
            if (_rawExtractedText.isNotEmpty) ...[
              Theme(
                data: Theme.of(context).copyWith(dividerColor: Colors.transparent),
                child: ExpansionTile(
                  title: const Text('Show Raw Recognized Text', style: TextStyle(color: Colors.white38, fontSize: 12)),
                  children: [
                    Container(
                      width: double.infinity,
                      padding: const EdgeInsets.all(12),
                      decoration: BoxDecoration(
                        color: const Color(0xFF0F172A),
                        borderRadius: BorderRadius.circular(12),
                      ),
                      child: Text(
                        _rawExtractedText,
                        style: const TextStyle(color: Colors.white54, fontSize: 11, fontFamily: 'monospace'),
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 24),
            ],

            // Submit Button
            SizedBox(
              width: double.infinity,
              height: 54,
              child: ElevatedButton(
                style: ElevatedButton.styleFrom(
                  backgroundColor: const Color(0xFF4F46E5),
                  foregroundColor: Colors.white,
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
                  elevation: 0,
                ),
                onPressed: _imageFile != null && !_isProcessing ? _submitReading : null,
                child: const Text(
                  'Confirm & Submit Reading',
                  style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
