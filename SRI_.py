from pathlib import Path
import subprocess
import time
import math
from RF24 import RF24,RF24_1MBPS, RF24_PA_LOW, RF24_DRIVER, RF24_PA_MAX, RF24_PA_HIGH, RF24_2MBPS
import struct
from typing import List
import os
import RPi.GPIO as GPIO
import logging
from threading import Timer
import zlib


# Configure logging for debugging transfer process
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Constants for radio configuration and transfer
SIZE = 32  # Maximum payload size for nRF24L01
HEADER_SIZE = 4  # 4 bytes: packet number (1 byte) + total packets in chunk (1 byte) + chunk number (1 byte) + total chunks (1 byte)
PAYLOAD_SIZE = SIZE - HEADER_SIZE  # Actual data size per packet
#USB_DIRECTORY = "/media/pi/KINGSTON"  # Mount point for USB drive
FILE_RECEIVED = "MTP-F24-SRI-C-RX"  # Name of output file
TOTAL_RUNTIME = 120  # 2 minute time limit
PIN_LED = [26,27,22]  # Pins of the LEDs. PIN_LED[1] es RX i PIN_LED[2] es TX i PIN_LED[0] es START Led
PIN_SWITCH = [17,23,24]    # Pins of the switches. PIN_SWITCH[0] es start i PIN_SWITCH[1] es Tx/Rx

AUTO_MOUNT_BASE = "/media"

def init_GPIO():
    GPIO.setmode(GPIO.BCM)
    # Configure the LED as an output and the switches as an input with pull-up resistance
    GPIO.setup(PIN_LED[0], GPIO.OUT)
    GPIO.setup(PIN_LED[1], GPIO.OUT)
    GPIO.setup(PIN_LED[2], GPIO.OUT)
    GPIO.setup(PIN_SWITCH[0], GPIO.IN, pull_up_down=GPIO.PUD_UP)
    GPIO.setup(PIN_SWITCH[1], GPIO.IN, pull_up_down=GPIO.PUD_UP)
    GPIO.setup(PIN_SWITCH[2], GPIO.IN, pull_up_down=GPIO.PUD_UP)
    return True

def find_usb_mount_point():
    """
    Busca el punto de montaje del USB en el directorio base de auto-montaje.
    Si no se encuentra, devuelve None.
    """
    for root, dirs, files in os.walk(AUTO_MOUNT_BASE):
        for dir in dirs:
            usb_path = os.path.join(root, dir)
            if os.path.ismount(usb_path):
                return usb_path
    return None

# def mount_usb():
    # """
    # Attempts to mount a USB drive.
    # Returns True if successful, False otherwise.
    # """
    # try:
        # # Look for USB device in /dev/
        # dev_files = os.listdir('/dev/')
        # usb_device = None
        # for file in dev_files:
            # # Look for sdX devices (typical USB naming)
            # if file.startswith('sd') and 'part' not in file:
                # usb_device = f'/dev/{file}'
                # break
        
        # if not usb_device:
            # logging.warning("No USB device found")
            # return False
        
        # # Try to mount the device
        # result = subprocess.run(
            # ['sudo', 'mount', usb_device, USB_DIRECTORY],
            # capture_output=True,
            # text=True
        # )
        # if result.returncode != 0:
            # logging.error(f"Mount error: {result.stderr}")
            # return False
        # return True
    # except Exception as e:
        # logging.error(f"Error mounting USB: {str(e)}")
        # return False
        
# def mount_usb():
    # """
    # Attempts to mount a USB drive.
    # Returns True if successful, False otherwise.
    # """
    # try:
        # # Look for USB device in /dev/
        # dev_files = os.listdir('/dev/')
        # usb_device = None
        # for file in dev_files:
            # # Look for sdX devices (typical USB naming)
            # if file.startswith('sd') and 'part' not in file:
                # usb_device = f'/dev/{file}1'  # Ensure you're mounting the correct partition (e.g., sda1)
                # break
        
        # if not usb_device:
            # logging.warning("No USB device found")
            # return False
        
        # # Check if the device is already mounted
        # result = subprocess.run(['mount', '--grep', usb_device], capture_output=True, text=True)
        # if result.returncode == 0:
            # logging.warning(f"{usb_device} is already mounted. Unmounting first.")
            # subprocess.run(['sudo', 'umount', usb_device], capture_output=True, text=True)
        
        # # Create mount directory if it doesn't exist
        # if not os.path.exists(USB_DIRECTORY):
            # os.makedirs(USB_DIRECTORY)
        
        # # Try to mount the device
        # result = subprocess.run(
            # ['sudo', 'mount', usb_device, USB_DIRECTORY],
            # capture_output=True,
            # text=True
        # )
        # if result.returncode != 0:
            # logging.error(f"Mount error: {result.stderr}")
            # return False
        # logging.info(f"USB mounted successfully at {USB_DIRECTORY}")
        # return True
    # except Exception as e:
        # logging.error(f"Error mounting USB: {str(e)}")
        # return False


def find_file():
    """
    Searches for a .txt file in the USB directory.
    Returns the path to the first .txt file found.
    """
    path = Path(find_usb_mount_point())
    for file in path.rglob('MTP-F24-SRI-C-TX.txt'):
        return str(file)
    return None

def init_radio():
    """
    Initializes the nRF24L01 radio with correct settings.
    Returns configured radio object and operation mode.
    """
    CSN_PIN = 0  # SPI bus 0
    if RF24_DRIVER == "MRAA":
        CE_PIN = 15
        # CE_PIN = 17
    elif RF24_DRIVER == "wiringPi":
        CE_PIN = 3
        # CE_PIN = 17
    else:
        CE_PIN = 22
        # CE_PIN = 17
        
    radio = RF24(CE_PIN, CSN_PIN)
    
    if not radio.begin(25, 0):
        #raise RuntimeError("Radio hardware not responding")
        GPIO.output(PIN_LED[0], GPIO.HIGH)
        GPIO.output(PIN_LED[1], GPIO.HIGH)
        GPIO.output(PIN_LED[2], GPIO.HIGH)
        time.sleep(0.5)
        GPIO.output(PIN_LED[0], GPIO.LOW)
        GPIO.output(PIN_LED[1], GPIO.LOW)
        GPIO.output(PIN_LED[2], GPIO.LOW)
        time.sleep(0.5)
        #Si falla que haga estas luces
    
    # Configure radio addresses
    address = [b"CNode1", b"CNode2"]

    #CONFIGURAR TX O RX
    #Espera a que el switch START estigui apagat (es veuen LEDS apagats, si està en posició ON es veuen leds tx rx encesos)
    while True:
        button_state0 = GPIO.input(PIN_SWITCH[0])
        
        if button_state0 == GPIO.LOW: # Si el botó start està encès, espera a que l'apaguis abans de triar Tx o Rx
            logging.info("START switch in OFF position, set TX or RX, then activate START switch.")
            break
        
        else:
            GPIO.output(PIN_LED[0], GPIO.LOW)
            logging.info("Waiting for the START switch to be turned off.")
            GPIO.output(PIN_LED[1], GPIO.HIGH)
            GPIO.output(PIN_LED[2], GPIO.HIGH)
            time.sleep(0.5)
            GPIO.output(PIN_LED[1], GPIO.LOW)
            GPIO.output(PIN_LED[2], GPIO.LOW)
            time.sleep(0.5)
    
    #Aquí ya estamos seguros de tener el switch de start en posición apagada (LOW)
    #Cuando movemos switch de START A ENCENDIDO , leemos si TX o RX.
    while True:
        button_state0 = GPIO.input(PIN_SWITCH[0])
        button_state1 = GPIO.input(PIN_SWITCH[1])
        button_state2 = GPIO.input(PIN_SWITCH[2])
        
        time.sleep(0.05)

        if button_state0 == GPIO.LOW: # Llegeix boto start. Si està activat entra --------------------------------> ha d'estar en low 
            logging.info ("He donat start")
            button_state = GPIO.input(PIN_SWITCH[1]) #mira posició TX/RX
            GPIO.output(PIN_LED[0], GPIO.HIGH) #LED de start activat
            time.sleep(0.05)
            # if button_state1 == GPIO.LOW: # Si està en mode Tx tornem un FALSE
                # logging.info("he arribat aqui")
                # GPIO.output(PIN_LED[0], GPIO.LOW) #LED de Tx activat
                # GPIO.output(PIN_LED[1], GPIO.HIGH)
                # radio_number = False
                # logging.info("TX SELECTED.")
                # break
            
            # elif button_state1 == GPIO.LOW: # Si està en mode Rx retornem un TRUE
                # GPIO.output(PIN_LED[2], GPIO.HIGH) #LED de Rx activat
                # radio_number = True
                # logging.info("RX SELECTED.")
                # break
        else:
            button_state = GPIO.input(PIN_SWITCH[1])
            if button_state1 == GPIO.LOW: # Si està en mode Tx tornem un FALSE
                GPIO.output(PIN_LED[2], GPIO.HIGH) #LED de Tx activat
                logging.info("he arribat aqui en tx")
                #GPIO.output(PIN_LED[0], GPIO.LOW) #LED de Tx activat
                GPIO.output(PIN_LED[1], GPIO.HIGH)
                radio_number = False
                logging.info("TX SELECTED.")
                break
                #GPIO.output(PIN_LED[1], GPIO.LOW) #LED de Rx desactiva
            elif button_state2 == GPIO.LOW: # Si està en mode Rx retornem un TRUE
                logging.info("he arribat aqui en rx")
                GPIO.output(PIN_LED[1], GPIO.HIGH) #LED de Rx activa
                #GPIO.output(PIN_LED[2], GPIO.HIGH) #LED de Rx activat
                radio_number = True
                logging.info("RX SELECTED.")
                break
                #GPIO.output(PIN_LED[2], GPIO.LOW) #LED de Tx desactiva
            time.sleep(0.1)
            #logging.info("No funciona")
            
        
    
    # Enable ACK payloads
    radio.enableAckPayload()
    radio.setPALevel(RF24_PA_MAX)  # RF24_PA_MAX is default. Change between different values to test. RF24_PA_HIGH (bit less than MAX, more stable)
    #PARAMETERS TO TEST:
    radio.setDataRate(RF24_2MBPS) # (por defecto 1 Mbps, pero 250 
    # kbps puede ir mejor para long range) , RF24_2MBPS , RF24_1MBPS , radio.setCRCLength(RF24_CRC_16) por defecto es RF24_CRC_8 pero alomejor 16 fitea bien
    # para el long MRM.. o para short , radio.setChannel(76) from 0 to 125 
    # Each channel corresponds to a 1 MHz increment, starting from 2.400 GHz (channel 0) up to 2.525 GHz (channel 125).,channel 76 por defecto 2,476 GHz
    # Recordar INCLUIRLO ARRIBA from RF24 import ... ,
    radio.setChannel(90)
    # Set up pipes for communication
    radio.openWritingPipe(address[radio_number])
    radio.openReadingPipe(1, address[not radio_number])
    radio.payloadSize = SIZE
    
    radio.printPrettyDetails()
    return radio, radio_number

def build_packets(file_buff: bytes, current_chunk: int, total_chunks: int) -> List[bytes]:
    """
    Splits file chunk into packets with enhanced headers.
    Format: [packet_number(1B), total_packets(1B), chunk_number(1B), total_chunks(1B), payload(28B)]
    """
    try:
        packet_buff = []
        length = len(file_buff)
        num_packets = math.ceil(length / PAYLOAD_SIZE)
        
        if num_packets > 255:
            raise ValueError(f"Chunk too large: requires {num_packets} packets, max is 255")
        
        for i in range(num_packets):
            # Enhanced header with chunk information
            header = struct.pack('BBBB', i, num_packets, current_chunk, total_chunks)
            
            start_idx = i * PAYLOAD_SIZE
            end_idx = min(start_idx + PAYLOAD_SIZE, length)
            payload = file_buff[start_idx:end_idx]
        
            if len(payload) < PAYLOAD_SIZE:
                payload = payload + b' ' * (PAYLOAD_SIZE - len(payload))
            packet = header + payload
                        
            packet_buff.append(packet)
            #logging.print("chunk comprimit enviat)
        
        return packet_buff
    except Exception as e:
        logging.error(f"Error building packets: {str(e)}")
        raise

def change_to_tx(radio):
    """Configures radio for transmission mode."""
    radio.stopListening()
    radio.flush_tx()
    return radio

def master(radio):
    """
    Enhanced transmitter function with completion detection and notification.
    """
    try:
        radio = change_to_tx(radio)
        
        while not find_usb_mount_point():
            logging.info("Waiting for USB...")
            time.sleep(2)
        
        file_path = find_file()
        #file_path = "MTP-F23-SRI-A-TX.txt"
        if not file_path:
            raise FileNotFoundError("No .txt file found on USB")
        print ({file_path})
        # Calculate file size and total chunks needed
        file_size = os.path.getsize(file_path)
        CHUNK_SIZE = 255 * PAYLOAD_SIZE
        total_chunks = math.ceil(file_size / CHUNK_SIZE)
        with open(file_path, 'rb') as f:
            for chunk_number in range(total_chunks):

                button_state0 = GPIO.input(PIN_SWITCH[0])
                if button_state0 == GPIO.LOW:
                    print("\n=== TRANSMISSION FINISHED BY START SWITCH ===")
                    GPIO.output(PIN_LED[0], GPIO.LOW)
                    GPIO.output(PIN_LED[2], GPIO.LOW)
                    return  # Exit when told by the start switch (competition time expired)
            
                file_chunk = f.read(CHUNK_SIZE)
                if not file_chunk:
                    break
                
                logging.info(f"Processing chunk {chunk_number+1}/{total_chunks}")
                chunk_compressed = zlib.compress(file_chunk)
                print (file_chunk)
                packet_buff = build_packets(chunk_compressed, chunk_number, total_chunks)

                for i, packet in enumerate(packet_buff):
                    
                    while True:
                        radio.write(packet)
                        
                        if radio.available():
                            length = radio.getDynamicPayloadSize()
                            ack = radio.read(length)
                            print (ack)
                            if len(ack) >= 1 and ack[0] == i:
                                break
                        else:
                            print ("no ack")
                        time.sleep(0.0001)  #SUBIR ESTE TIMEOUT? Caso de no recibir ACK. La RETRANSMISIón hacerla más lenta? 0.1 es muypoco?
                if int(chunk_number) % 2 == 0:
                    GPIO.output(PIN_LED[2], GPIO.HIGH) #Parpalleja en cada chunk enviat
                else:
                    GPIO.output(PIN_LED[2], GPIO.LOW)
                
                if chunk_number == total_chunks-1:
                    print("\n=== TRANSMISSION OF FILE FINISHED ===")
                    GPIO.output(PIN_LED[0], GPIO.LOW)
                    GPIO.output(PIN_LED[1], GPIO.LOW)
                    GPIO.output(PIN_LED[2], GPIO.LOW)
                    return  # Exit early after successful transmission
                
    except Exception as e:
        logging.error(f"Error in master: {str(e)}")
        logging.error("no troba el fitxer")
    finally:
        try:
            subprocess.run(["sudo","umount", find_usb_mount_point()])
        except:
            pass

def slave(radio):
    """
    Enhanced receiver function with completion detection and notification.
    """
    try:
        radio.startListening()
        chunks_received = {}  # Dictionary to store received chunks
        chunks_decompressed = {}
        current_chunk = 0
        total_chunks = None
        next_packet = 0
        radio.writeAckPayload(1, struct.pack('B', next_packet))
        
        def save_file(is_complete=False):
            """Helper function to save received chunks"""
            if not chunks_received:
                logging.warning("No chunks received to save")
                return
            
            if not find_usb_mount_point():
                logging.error("USB no montado. No se puede guardar el archivo.")
                return
            
            final_data = bytearray()
            # Sort chunks by number to maintain order
            for i in sorted(chunks_received.keys()):
                try:
                    chunks_decompressed[i] = zlib.decompress(chunks_received[i])
                    final_data.extend(chunks_decompressed[i])
                except zlib.error as e:
                    print("Error al descomprimir l'última part")
                    continue
            # Choose filename based on completion status
            if is_complete:
                filename = f"{FILE_RECEIVED}.txt"
                logging.info(f"=== FULL FILE RECEIVED: {len(chunks_received)}/{total_chunks} chunks ===")
            else:
                filename = f"{FILE_RECEIVED}_partial.txt"
                logging.info(f"Saving partial file with {len(chunks_received)}/{total_chunks} chunks")
            
            # Save file to USB
            usb_path = os.path.join(find_usb_mount_point(), filename)
            with open(usb_path, 'wb') as file:
                file.write(final_data)
            logging.info(f"Archivo guardado en USB como: {usb_path}")

            #try to copy to USB using original mounting method
            # if mount_usb():
                # try:
                    # subprocess.run(["cp", filename, f"{USB_DIRECTORY}/{filename}"])
                    # subprocess.run(["sudo", "umount", USB_DIRECTORY])
                # except Exception as e:
                    # logging.error(f"Error copying to USB: {str(e)}")
        
        while not current_chunk == total_chunks:

            button_state0 = GPIO.input(PIN_SWITCH[0])
            if button_state0 == GPIO.LOW:
                print("\n=== RECEPTION FINISHED BY START SWITCH ===")
                GPIO.output(PIN_LED[0], GPIO.LOW)
                GPIO.output(PIN_LED[2], GPIO.LOW)
                break  # Exit when told by the start switch (competition time expired)
            
            if radio.available():
                payload = radio.read(SIZE)
                # Extract enhanced header information
                packet_num, total_packets, chunk_num, chunks_total = struct.unpack('BBBB', payload[:HEADER_SIZE])

                if total_chunks is None:
                    total_chunks = chunks_total
                    logging.info(f"Expecting {total_chunks} total chunks")
                
                # Process only if it's the packet we're expecting
                if packet_num == next_packet:
                    if chunk_num not in chunks_received:
                        chunks_received[chunk_num] = bytearray()
                        chunks_decompressed [chunk_num] = bytearray()
                    
                    data = payload[HEADER_SIZE:]
                                        
                    chunks_received[chunk_num].extend(data)
                    if packet_num == total_packets - 1:  # Last packet in chunk
                        next_packet = 0
                        current_chunk += 1                        
                        logging.info(f"Completed chunk {chunk_num}, {len(chunks_received)}/{total_chunks} chunks received")
                    else:
                        next_packet += 1

                
                radio.writeAckPayload(1, struct.pack('B', next_packet))
                if int(chunk_num) % 2 == 0:
                    GPIO.output(PIN_LED[1], GPIO.HIGH) #Parpalleja en cada chunk enviat
                else:
                    GPIO.output(PIN_LED[1], GPIO.LOW)
                
        # Check if we have received all chunks
        if total_chunks is not None and len(chunks_received) == total_chunks:
            save_file(is_complete=True)
            GPIO.output(PIN_LED[0], GPIO.LOW)
            return
               
        # If we get here, TOTAL_RUNTIME elapsed - save partial file
        if chunks_received:
            save_file(is_complete=False)
            GPIO.output(PIN_LED[0], GPIO.LOW)
        
    except Exception as e:
        logging.error(f"Error in slave: {str(e)}")
        if chunks_received:
            logging.info("Attempting to save partial file after error")
            save_file(is_complete=False)
            GPIO.output(PIN_LED[0], GPIO.LOW)
    finally:
        radio.stopListening()
        GPIO.output(PIN_LED[1], GPIO.LOW)
        GPIO.output(PIN_LED[0], GPIO.LOW)
        #pi.stop()

def set_role(radio, mode) -> bool:
    """Sets the radio role based on user input."""
    if mode == 1:
        slave(radio)
        return True
    else:
        master(radio)
        return True

if __name__ == "__main__":
    init_GPIO()
    radio, mode = init_radio()
    try:
        set_role(radio, mode)
        GPIO.cleanup()
        radio.powerDown()
    except KeyboardInterrupt:
        print("Keyboard Interrupt detected. Powering down radio.")
        GPIO.cleanup()
        radio.powerDown()
else:
    print("Run slave() on receiver\nRun master() on transmitter")
